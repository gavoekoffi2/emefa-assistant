"""Nightly consolidation — the second look at what was said.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

Live extraction sees one turn at a time, and one turn is often not enough. A
fact stated across three exchanges ("on a un nouveau client" … "c'est une
clinique" … "à Kara") is invisible per-turn and obvious in aggregate. So the
whole day gets re-read once, in batches, against the same closed vocabulary.

Everything about this pass is bounded, because it is autonomous work spending
the user's money while they sleep (CLAUDE.md §34):

* it only looks at events since the last consolidation, never the whole log;
* it processes at most `MAX_EVENTS` of them, oldest first;
* it groups them into a small number of batches;
* it records its own completion as an event, so a crashed pass resumes from
  where it stopped rather than re-reading — and so the watermark needs no
  extra table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from emefa.domain.memories import MemoryRepository
from emefa.domain.memory.ingest import MemoryIngestor

#: Event type marking a completed pass. Doubles as the watermark.
CONSOLIDATION_EVENT = "consolidation_completed"

#: Hard ceiling on one night's work.
MAX_EVENTS = 120
#: Events per extraction call. Large enough for a claim to span turns, small
#: enough to stay well inside the extractor's transcript cap.
BATCH_SIZE = 12
#: How far back a first-ever run reaches. Without this, the first pass on an
#: instance with months of history would re-read all of it in one go.
FIRST_RUN_WINDOW_DAYS = 7


@dataclass(frozen=True, slots=True)
class ConsolidationReport:
    events_read: int = 0
    batches: int = 0
    created: int = 0
    reinforced: int = 0
    superseded: int = 0
    error: str | None = None

    @property
    def facts_touched(self) -> int:
        return self.created + self.reinforced + self.superseded


class ConsolidationPass:
    def __init__(self, memories: MemoryRepository, ingestor: MemoryIngestor) -> None:
        self.memories = memories
        self.ingestor = ingestor

    def watermark(self, now: datetime | None = None) -> str:
        """Timestamp of the last completed pass, or the start of the first-run
        window when there has never been one."""
        reference = now or datetime.now(timezone.utc)
        for event in self.memories.kernel.recent_events(limit=50):
            if event.type == CONSOLIDATION_EVENT:
                return event.created_at
        return (reference - timedelta(days=FIRST_RUN_WINDOW_DAYS)).isoformat()

    async def run(self, now: datetime | None = None) -> ConsolidationReport:
        reference = now or datetime.now(timezone.utc)
        since = self.watermark(reference)
        events = [
            event
            for event in self.memories.kernel.recent_events(limit=MAX_EVENTS, since=since)
            if event.type != CONSOLIDATION_EVENT
        ]
        if not events:
            self._mark_complete(0, 0)
            return ConsolidationReport()

        events.reverse()  # oldest first, so a claim reads in the order it was made
        created = reinforced = superseded = 0
        batches = 0
        error: str | None = None

        for start in range(0, len(events), BATCH_SIZE):
            batch = events[start : start + BATCH_SIZE]
            transcript = "\n".join(f"[{event.source}] {event.content}" for event in batch)
            result = await self.ingestor.ingest(
                transcript,
                source="consolidation",
                # The events are already in the log; re-logging the batch would
                # make the next pass read its own output.
                log_event=False,
            )
            batches += 1
            created += result.created
            reinforced += result.reinforced
            superseded += result.superseded
            if result.error is not None:
                error = result.error

        self._mark_complete(len(events), created + reinforced + superseded)
        return ConsolidationReport(
            events_read=len(events),
            batches=batches,
            created=created,
            reinforced=reinforced,
            superseded=superseded,
            error=error,
        )

    def _mark_complete(self, events_read: int, facts_touched: int) -> None:
        self.memories.log_event(
            type=CONSOLIDATION_EVENT,
            source="scheduler",
            content=f"{events_read} évènements relus, {facts_touched} faits mis à jour",
            metadata={"events_read": events_read, "facts_touched": facts_touched},
        )
