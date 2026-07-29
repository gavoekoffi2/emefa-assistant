# Credits

EMEFA is an original work. Some of its subsystems were designed after studying other
open-source projects. This file records that debt, whether or not the licence requires it.

## Jarvis OS — Barthélemy Houot

<https://github.com/Grominet95/jarvis-OS> · GNU AGPL-3.0-or-later

The following EMEFA subsystems are **informed by** Jarvis OS's design:

| EMEFA subsystem | Idea taken |
|---|---|
| Memory Kernel (`backend/emefa/domain/memory/`) | Atomic dated sourced facts; reinforcement by observation instead of duplication; supersession instead of deletion; salience as `importance × recency × relevance × confidence`; per-category decay half-lives |
| Proactive engine | Initiatives as governed objects carrying an autonomy level 0–5, a cost ceiling and a permission category; level 5 always requiring human validation; a nightly curator |
| Mission engine | Plan → step → verification → resume, with verification split into structural, deterministic and semantic checks |
| Budget guard | Per-scope spend accounting seeded from history, with thresholds and a hard stop |

**No source code from Jarvis OS is present in EMEFA.** These subsystems are re-implemented
from their design, for the reasons recorded in
[`adr/ADR-004-external-project-licensing.md`](adr/ADR-004-external-project-licensing.md).

Jarvis OS's authentication model was audited and **deliberately not adopted**; the
reasoning is in [`adr/ADR-002-account-authentication.md`](adr/ADR-002-account-authentication.md).

## jarvis-skills — Barth (BarthH95)

<https://github.com/Grominet95/jarvis-skills> · MIT

EMEFA's skill manifest format and catalogue index follow the `jarvis-skills` standard
(`schema_version: "1.0"`), so skills written for that catalogue remain loadable. Reused
MIT material carries its notice alongside it.

## MediaPipe — Google

<https://github.com/google-ai-edge/mediapipe> · Apache-2.0

The canonical 468-point face mesh bundled at
`web/public/models/emefa-canonical-face.obj` is derived from MediaPipe's canonical face
model.
