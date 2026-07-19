FROM node:22-alpine AS web-build
WORKDIR /build/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EMEFA_WEB_DIST_PATH=/app/web/dist
WORKDIR /app
RUN useradd --create-home --uid 10001 emefa
COPY backend/pyproject.toml ./backend/
COPY backend/emefa ./backend/emefa
RUN pip install --no-cache-dir ./backend
COPY --from=web-build /build/web/dist ./web/dist
RUN mkdir -p /app/data && chown -R emefa:emefa /app
USER emefa
EXPOSE 8000
CMD ["uvicorn", "emefa.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
