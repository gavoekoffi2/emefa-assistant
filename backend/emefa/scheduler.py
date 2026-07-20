"""Bounded recurring-work scheduler (Phase 8 seed).

One explicit job: the proactive morning brief. The loop sleeps until the
configured local hour, runs one idempotent job iteration with its own
error handling, and is cancelled cleanly at shutdown — no unbounded
autonomous behavior. E-mailing the brief only happens when the owner has
granted a standing, scoped approval via EMEFA_BRIEF_EMAIL_TO.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

from emefa.domain.briefings import BriefingRepository
from emefa.domain.profiles import ProfileRepository
from emefa.domain.prospects import ProspectRepository
from emefa.domain.tasks import TaskRepository
from emefa.infrastructure.email import SmtpEmailSender
from emefa.observability import audit
from emefa.skills import compose_daily_brief, format_brief_text


def seconds_until_hour(hour: int, now: datetime) -> float:
    """Seconds from now until the next occurrence of the given local hour."""
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_brief_job(
    profiles: ProfileRepository,
    tasks: TaskRepository,
    prospects: ProspectRepository,
    briefings: BriefingRepository,
    email_sender: SmtpEmailSender | None = None,
    email_to: str | None = None,
) -> dict[str, Any]:
    """Generate and store today's brief once; e-mail it only under the
    standing approval, and only once per day."""
    today = date.today().isoformat()
    existing = briefings.get(today)
    if existing is None:
        brief = compose_daily_brief(profiles, tasks, prospects)
        stored = briefings.save(today, brief)
        audit("brief_generated", brief_date=today)
    else:
        stored = existing
    emailed = stored.emailed
    if email_to and email_sender is not None and email_sender.configured and not emailed:
        try:
            result = await email_sender.send(
                email_to,
                f"Votre brief EMEFA du {today}",
                format_brief_text(stored.content),
            )
        except Exception:
            audit("brief_email_failed", brief_date=today)
        else:
            if result.get("accepted"):
                briefings.mark_emailed(today)
                emailed = True
                audit("brief_emailed", brief_date=today)
            else:
                audit("brief_email_refused", brief_date=today)
    return {"brief_date": today, "emailed": emailed}


async def brief_scheduler_loop(
    hour: int,
    profiles: ProfileRepository,
    tasks: TaskRepository,
    prospects: ProspectRepository,
    briefings: BriefingRepository,
    email_sender: SmtpEmailSender | None,
    email_to: str | None,
) -> None:
    while True:
        delay = seconds_until_hour(hour, datetime.now())
        await asyncio.sleep(delay)
        try:
            await run_brief_job(
                profiles, tasks, prospects, briefings, email_sender, email_to
            )
        except Exception:  # one failed run must not kill the schedule
            audit("brief_job_failed")
        # Guard against clock edge cases: never loop more than once a minute.
        await asyncio.sleep(60)
