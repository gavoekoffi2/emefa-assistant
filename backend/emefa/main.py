"""Application factory for the greenfield EMEFA backend."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from emefa import __version__
from emefa.api.agent import router as agent_router
from emefa.api.devices import router as devices_router
from emefa.api.realtime import router as realtime_router
from emefa.api.web_session import router as web_session_router
from emefa.config import Settings
from emefa.domain.agent import AgentEngine, AgentStep, Brain, ToolShelf
from emefa.domain.devices import DeviceRepository
from emefa.domain.ratelimit import FailureLimiter
from emefa.infrastructure.deepseek import DeepSeekBrain
from emefa.infrastructure.realtime import RealtimeGateway
from emefa.observability import (
    configure_logging,
    monotonic_ms,
    new_request_id,
    request_id_var,
)

request_logger = logging.getLogger("emefa.request")


class NotConfiguredBrain:
    async def think(self, history, tools) -> AgentStep:
        return AgentStep(answer="Le moteur de langage EMEFA n’est pas encore configuré.")


def create_app(settings: Settings | None = None, brain: Brain | None = None) -> FastAPI:
    configure_logging()
    active_settings = settings or Settings()
    selected_brain: Brain
    if brain is not None:
        selected_brain = brain
    elif (
        active_settings.deepseek_api_key is not None
        and active_settings.deepseek_api_key.get_secret_value().strip()
    ):
        selected_brain = DeepSeekBrain(
            api_key=active_settings.deepseek_api_key.get_secret_value().strip(),
            model=active_settings.deepseek_model,
        )
    else:
        selected_brain = NotConfiguredBrain()

    realtime_key = (
        active_settings.elevenlabs_api_key.get_secret_value().strip()
        if active_settings.elevenlabs_api_key is not None
        else None
    )
    realtime_gateway = RealtimeGateway(
        api_key=realtime_key,
        agent_id=active_settings.elevenlabs_agent_id,
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        yield
        close = getattr(selected_brain, "close", None)
        if close is not None:
            await close()
        await realtime_gateway.close()

    application = FastAPI(
        title="EMEFA",
        version=__version__,
        description="Private API for the EMEFA personal assistant",
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.devices = DeviceRepository(active_settings.database_path)
    application.state.agent = AgentEngine(selected_brain, ToolShelf())
    application.state.realtime = realtime_gateway
    application.state.activation_limiter = FailureLimiter(
        max_failures=active_settings.activation_max_failures,
        window_seconds=active_settings.activation_window_seconds,
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = new_request_id()
        token = request_id_var.set(request_id)
        started = monotonic_ms()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        if request.url.path.startswith(("/v1/", "/health")):
            request_logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(monotonic_ms() - started, 1),
                },
            )
        return response

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; "
            "connect-src 'self' https://api.elevenlabs.io wss://api.elevenlabs.io; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "emefa-backend",
            "version": __version__,
        }

    application.include_router(devices_router)
    application.include_router(web_session_router)
    application.include_router(agent_router)
    application.include_router(realtime_router)
    if active_settings.web_dist_path is not None and active_settings.web_dist_path.is_dir():
        application.mount(
            "/",
            StaticFiles(directory=str(active_settings.web_dist_path), html=True),
            name="web",
        )
    return application


app = create_app()
