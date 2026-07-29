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

from emefa.domain.agenda import AgendaRepository
from emefa.domain.briefings import BriefingRepository
from emefa.domain.crm import CrmRepository
from emefa.domain.email import EmailProvider
from emefa.domain.meetings import MeetingRepository
from emefa.domain.memory.consolidation import ConsolidationPass
from emefa.domain.proactive import ProactiveEngine
from emefa.domain.profiles import ProfileRepository
from emefa.domain.prospects import ProspectRepository
from emefa.domain.reports import (
    ReportPreferencesRepository,
    compose_evening_report,
    compose_morning_brief,
    format_evening_text,
    format_morning_text,
)
from emefa.domain.tasks import TaskRepository
from emefa.observability import audit


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
    email_provider: EmailProvider | None = None,
    email_to: str | None = None,
    crm: CrmRepository | None = None,
    meetings: MeetingRepository | None = None,
    preferences: ReportPreferencesRepository | None = None,
    agenda: AgendaRepository | None = None,
) -> dict[str, Any]:
    """Generate and store today's brief once; e-mail it only under the
    standing approval, and only once per day."""
    today = date.today().isoformat()
    existing = briefings.get(today)
    if existing is None:
        brief = compose_morning_brief(
            profiles,
            tasks,
            prospects,
            crm,
            meetings,
            preferences.get() if preferences is not None else None,
            agenda=agenda,
        )
        stored = briefings.save(today, brief)
        audit("brief_generated", brief_date=today)
    else:
        stored = existing
    return await _deliver(
        briefings,
        stored,
        today,
        email_provider,
        email_to,
        subject=f"Votre brief EMEFA du {today}",
        body=format_morning_text(stored.content),
        label="brief",
    )


async def run_evening_job(
    profiles: ProfileRepository,
    tasks: TaskRepository,
    reports: BriefingRepository,
    email_provider: EmailProvider | None = None,
    email_to: str | None = None,
    crm: CrmRepository | None = None,
    meetings: MeetingRepository | None = None,
    preferences: ReportPreferencesRepository | None = None,
    agenda: AgendaRepository | None = None,
) -> dict[str, Any]:
    """Same contract as the morning job, for the end-of-day report."""
    today = date.today().isoformat()
    # The evening report is *regenerated* rather than reused: it summarises a
    # day that is still moving, so a rerun must reflect the latest state.
    report = compose_evening_report(
        profiles,
        tasks,
        crm,
        meetings,
        preferences.get() if preferences is not None else None,
        agenda=agenda,
    )
    existing = reports.get(today)
    stored = reports.save(today, report)
    if existing is not None and existing.emailed:
        stored = reports.get(today) or stored
    audit("evening_report_generated", brief_date=today)
    return await _deliver(
        reports,
        stored,
        today,
        email_provider,
        email_to,
        subject=f"Votre rapport du soir EMEFA — {today}",
        body=format_evening_text(stored.content),
        label="evening_report",
    )


async def _deliver(
    repository: BriefingRepository,
    stored: Any,
    today: str,
    email_provider: EmailProvider | None,
    email_to: str | None,
    subject: str,
    body: str,
    label: str,
) -> dict[str, Any]:
    emailed = stored.emailed
    if email_to and email_provider is not None and not emailed:
        try:
            result = await asyncio.to_thread(email_provider.send, email_to, subject, body)
        except Exception:
            audit(f"{label}_email_failed", brief_date=today)
        else:
            if result.get("status") == "sent":
                repository.mark_emailed(today)
                emailed = True
                audit(f"{label}_emailed", brief_date=today)
            else:
                audit(f"{label}_email_refused", brief_date=today)
    return {"brief_date": today, "emailed": emailed}


async def brief_scheduler_loop(
    hour: int,
    profiles: ProfileRepository,
    tasks: TaskRepository,
    prospects: ProspectRepository,
    briefings: BriefingRepository,
    email_provider: EmailProvider | None,
    email_to: str | None,
    crm: CrmRepository | None = None,
    meetings: MeetingRepository | None = None,
    preferences: ReportPreferencesRepository | None = None,
    agenda: AgendaRepository | None = None,
) -> None:
    while True:
        delay = seconds_until_hour(hour, datetime.now())
        await asyncio.sleep(delay)
        try:
            await run_brief_job(
                profiles, tasks, prospects, briefings, email_provider, email_to,
                crm, meetings, preferences, agenda,
            )
        except Exception:  # one failed run must not kill the schedule
            audit("brief_job_failed")
        # Guard against clock edge cases: never loop more than once a minute.
        await asyncio.sleep(60)


async def evening_scheduler_loop(
    hour: int,
    profiles: ProfileRepository,
    tasks: TaskRepository,
    reports: BriefingRepository,
    email_provider: EmailProvider | None,
    email_to: str | None,
    crm: CrmRepository | None = None,
    meetings: MeetingRepository | None = None,
    preferences: ReportPreferencesRepository | None = None,
    agenda: AgendaRepository | None = None,
) -> None:
    while True:
        delay = seconds_until_hour(hour, datetime.now())
        await asyncio.sleep(delay)
        try:
            await run_evening_job(
                profiles, tasks, reports, email_provider, email_to,
                crm, meetings, preferences, agenda,
            )
        except Exception:
            audit("evening_job_failed")
        await asyncio.sleep(60)


async def consolidation_scheduler_loop(
    hour: int,
    consolidation: ConsolidationPass,
) -> None:
    """Run the bounded factual-memory consolidation pass once a night."""
    while True:
        await asyncio.sleep(seconds_until_hour(hour, datetime.now()))
        try:
            report = await consolidation.run()
        except Exception:
            audit("memory_consolidation_failed")
        else:
            audit(
                "memory_consolidation_completed",
                events_read=report.events_read,
                created=report.created,
                reinforced=report.reinforced,
                superseded=report.superseded,
                error=report.error,
            )
        await asyncio.sleep(60)


async def proactive_scheduler_loop(
    interval_minutes: int,
    engine: ProactiveEngine,
) -> None:
    """Run bounded proactive collection passes on a fixed interval."""
    delay = max(60.0, interval_minutes * 60.0)
    while True:
        await asyncio.sleep(delay)
        try:
            report = engine.run()
        except Exception:
            audit("proactive_pass_failed")
        else:
            audit(
                "proactive_pass",
                raised=report.raised,
                duplicates=report.duplicates,
                expired=report.expired,
                skipped_budget=report.skipped_budget,
            )
