#!/usr/bin/env python3
"""EMEFA — smoke-test de staging (validation post-déploiement).

Vérifie automatiquement, contre une instance EMEFA déjà déployée, autant que
possible du parcours critique — sans jamais rien envoyer de réel ni exécuter
d'action destructive.

Principes (voir CLAUDE.md §25 « No Fake Completion » et §36 « Testing ») :
- échoue explicitement (code de sortie ≠ 0) si une étape CRITIQUE échoue ;
- n'affiche jamais PASS pour une capacité qui n'a pas réellement été testée :
  une étape non exécutable est marquée SKIP (raison) ou MANUAL REQUIRED ;
- n'utilise que des données de test identifiables (préfixe « ZZ-SMOKE ») et les
  nettoie quand c'est possible sans risque ;
- n'envoie jamais de vrai e-mail : le mécanisme d'approbation est testé par la
  voie du REFUS (jamais l'approbation d'un envoi) ;
- n'expose aucun secret (ni le code d'activation, ni le cookie de session).

Certaines capacités d'écriture passent par le cerveau LLM gouverné (compétences
`remember`, `add_prospect`, `email_send`). Elles ne sont tentées que si le
moteur agent est configuré sur l'instance cible ; sinon elles sont marquées
SKIP, jamais simulées comme réussies.

Usage :
    python3 scripts/staging_smoke_test.py \
        --base-url https://emefa.exemple.tld \
        --enrollment-code "<code privé>"

Le code d'activation peut aussi venir de la variable d'environnement
EMEFA_ENROLLMENT_CODE, ou être saisi de façon masquée si le terminal est
interactif. Ajoutez --no-writes pour un passage strictement en lecture seule.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

# ── Sortie lisible ───────────────────────────────────────────────────────────
_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


PASS = _c("32", "PASS")
FAIL = _c("31", "FAIL")
SKIP = _c("33", "SKIP")
WARN = _c("33", "WARN")
INFO = _c("36", "INFO")
MANUAL = _c("35", "MANUAL REQUIRED")


class Report:
    """Collecte les résultats et calcule le code de sortie."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.warned = 0
        self.critical_failed = False

    def ok(self, step: str, detail: str = "") -> None:
        self.passed += 1
        print(f"  [{PASS}] {step}{_suffix(detail)}")

    def fail(self, step: str, detail: str = "", *, critical: bool = False) -> None:
        self.failed += 1
        if critical:
            self.critical_failed = True
        tag = f"{FAIL} (CRITIQUE)" if critical else FAIL
        print(f"  [{tag}] {step}{_suffix(detail)}")

    def skip(self, step: str, detail: str = "") -> None:
        self.skipped += 1
        print(f"  [{SKIP}] {step}{_suffix(detail)}")

    def warn(self, step: str, detail: str = "") -> None:
        self.warned += 1
        print(f"  [{WARN}] {step}{_suffix(detail)}")

    def info(self, step: str, detail: str = "") -> None:
        print(f"  [{INFO}] {step}{_suffix(detail)}")


def _suffix(detail: str) -> str:
    return f" — {detail}" if detail else ""


def section(title: str) -> None:
    print(f"\n{_c('1', title)}")


# ── Client HTTP minimal (cookies de session, aucun secret journalisé) ────────
class Client:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> tuple[int, Any]:
        """Renvoie (status_code, payload_json_ou_texte). Ne lève pas sur 4xx/5xx."""
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as resp:
                return resp.status, _decode(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _decode(exc.read())


def _decode(raw: bytes) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _detail(payload: Any) -> str:
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])
    if isinstance(payload, str):
        return payload[:200]
    return ""


# ── Étapes ───────────────────────────────────────────────────────────────────
def step_health(client: Client, report: Report) -> bool:
    section("[1] Démarrage & /health")
    try:
        status, payload = client.request("GET", "/health")
    except (urllib.error.URLError, OSError) as exc:
        report.fail("Service injoignable", str(exc), critical=True)
        return False
    if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
        report.ok("Service en ligne", f"version {payload.get('version', '?')}")
        return True
    report.fail("Réponse /health inattendue", f"HTTP {status}", critical=True)
    return False


def step_activate(client: Client, report: Report, code: str) -> bool:
    section("[2] Activation de la session privée")
    status, payload = client.request(
        "POST",
        "/v1/web/session",
        {"name": "ZZ-SMOKE-TEST", "enrollment_code": code},
    )
    if status == 201:
        report.ok("Session activée (cookie reçu)")
        return True
    hints = {
        403: "code d'activation invalide",
        409: "limite de navigateurs atteinte — révoquez un appareil ou attendez",
        503: "activation non configurée (EMEFA_ENROLLMENT_CODE absent côté serveur)",
    }
    report.fail(
        "Activation refusée",
        f"HTTP {status} : {hints.get(status, _detail(payload))}",
        critical=True,
    )
    return False


def step_system(client: Client, report: Report) -> dict[str, Any]:
    section("[3] État système & configuration cerveau/voix")
    status, payload = client.request("GET", "/v1/system/status")
    if status != 200 or not isinstance(payload, dict):
        report.fail("Statut système indisponible", f"HTTP {status}", critical=True)
        return {}
    skills = payload.get("skills", [])
    report.ok(
        "Statut système lu",
        f"schema v{payload.get('schema_version')}, "
        f"{len(skills)} compétence(s), "
        f"{payload.get('open_task_count')} tâche(s) ouverte(s)",
    )
    report.info(
        "Cerveau texte",
        "configuré" if payload.get("brain_configured") else "NON configuré (LLM absent)",
    )
    report.info(
        "Voix temps réel",
        "configurée" if payload.get("voice_configured") else "NON configurée (ElevenLabs absent)",
    )
    return payload


def step_onboarding(client: Client, report: Report) -> None:
    section("[4] Onboarding — profil assistante & métier (lecture)")
    status, profile = client.request("GET", "/v1/assistant/profile")
    if status == 200 and isinstance(profile, dict):
        report.ok("Profil assistante lisible", f"nom « {profile.get('name', '?')} »")
    else:
        report.fail("Profil assistante illisible", f"HTTP {status}")
    status, business = client.request("GET", "/v1/assistant/business")
    if status == 200 and isinstance(business, dict):
        empty = not any(
            str(business.get(k, "")).strip()
            for k in ("owner_name", "company_name", "offer", "target_customers")
        )
        report.ok(
            "Profil métier lisible",
            "vierge (onboarding à faire)" if empty else "renseigné",
        )
    else:
        report.fail("Profil métier illisible", f"HTTP {status}")
    report.info(
        "Onboarding conversationnel (guidé par le cerveau)",
        "non couvert automatiquement — voir MANUAL REQUIRED",
    )


def step_memory(
    client: Client, report: Report, brain: bool, allow_writes: bool
) -> None:
    section("[5] Mémoire durable — lecture, export, cycle create/read/forget")
    status, memories = client.request("GET", "/v1/memories")
    if status == 200 and isinstance(memories, list):
        report.ok("Liste des souvenirs lisible", f"{len(memories)} souvenir(s)")
    else:
        report.fail("Liste des souvenirs illisible", f"HTTP {status}")
    status, export = client.request("GET", "/v1/memories/export")
    if status == 200 and isinstance(export, dict) and "memories" in export:
        report.ok("Export mémoire fonctionnel", f"{export.get('count')} entrée(s)")
    else:
        report.fail("Export mémoire cassé", f"HTTP {status}")

    if not brain:
        report.skip(
            "Cycle create/read/forget",
            "cerveau non configuré — la création passe par la compétence LLM `remember`",
        )
        return
    if not allow_writes:
        report.skip("Cycle create/read/forget", "--no-writes")
        return

    marker = f"ZZ-SMOKE mémoire témoin {uuid.uuid4().hex[:8]}"
    status, run = client.request(
        "POST",
        "/v1/agent/runs",
        {"message": f"Retiens ce fait de test, exactement : « {marker} »."},
        timeout=90,
    )
    if status != 200:
        report.warn("Création via cerveau", f"HTTP {status} sur /v1/agent/runs")
        return
    # Le souvenir est écrit de façon synchrone si le LLM appelle l'outil.
    _, memories = client.request("GET", "/v1/memories")
    hit = next(
        (m for m in memories if isinstance(m, dict) and marker in m.get("content", "")),
        None,
    ) if isinstance(memories, list) else None
    if hit is None:
        report.warn(
            "Cycle create/read/forget",
            "le cerveau n'a pas créé le souvenir témoin (LLM n'a pas appelé `remember`) — non vérifié",
        )
        return
    report.ok("Création + lecture du souvenir témoin")
    status, _ = client.request("DELETE", f"/v1/memories/{hit['memory_id']}")
    if status != 204:
        report.fail("Oubli (DELETE) du souvenir témoin", f"HTTP {status}")
        report.info("Nettoyage manuel requis", f"souvenir « {marker} »")
        return
    _, memories = client.request("GET", "/v1/memories")
    still = isinstance(memories, list) and any(
        isinstance(m, dict) and marker in m.get("content", "") for m in memories
    )
    if still:
        report.fail("Oubli non effectif", f"souvenir « {marker} » toujours présent")
    else:
        report.ok("Oubli vérifié (données de test nettoyées)")


def step_briefing(client: Client, report: Report) -> None:
    section("[6] Brief du jour — endpoint")
    status, payload = client.request("GET", "/v1/briefings/today")
    if status == 200 and isinstance(payload, dict):
        report.ok(
            "Brief du jour présent",
            f"date {payload.get('brief_date')}, envoyé par e-mail : {payload.get('emailed')}",
        )
    elif status == 404:
        report.ok(
            "Endpoint brief joignable",
            "aucun brief aujourd'hui (génération pilotée par le planificateur/l'heure)",
        )
    else:
        report.fail("Endpoint brief cassé", f"HTTP {status}")
    report.info(
        "Génération réelle du brief",
        "dépend de EMEFA_BRIEF_HOUR et de l'heure serveur — non forçable via l'API",
    )


def step_approvals(
    client: Client, report: Report, brain: bool, skills: set[str], allow_writes: bool
) -> None:
    section("[7] Mécanisme d'approbation — liste & round-trip par REFUS")
    status, pending = client.request("GET", "/v1/agent/approvals")
    if status == 200 and isinstance(pending, list):
        report.ok("Liste des approbations en attente lisible", f"{len(pending)} en attente")
    else:
        report.fail("Liste des approbations illisible", f"HTTP {status}")
        return

    if not brain:
        report.skip("Round-trip d'approbation", "cerveau non configuré")
        return
    if "email_send" not in skills:
        report.skip("Round-trip d'approbation", "compétence e-mail non connectée sur l'instance")
        return
    if not allow_writes:
        report.skip("Round-trip d'approbation", "--no-writes")
        return

    # On demande un envoi d'e-mail (action COMMUNICATE) : il DOIT s'arrêter en
    # confirmation_required. On le REFUSE ensuite — jamais d'approbation, donc
    # aucun e-mail réel ne part.
    status, run = client.request(
        "POST",
        "/v1/agent/runs",
        {
            "message": (
                "Envoie un e-mail à zz-smoke-test@example.invalid, "
                "objet « ZZ-SMOKE test », corps « test de smoke, ne pas envoyer »."
            )
        },
        timeout=90,
    )
    if status != 200 or not isinstance(run, dict):
        report.warn("Round-trip d'approbation", f"HTTP {status} sur /v1/agent/runs")
        return
    if run.get("status") != "confirmation_required" or not run.get("action_id"):
        report.warn(
            "Round-trip d'approbation",
            f"le cerveau n'a pas déclenché de confirmation (statut « {run.get('status')} ») — non vérifié",
        )
        return
    report.ok("Action à conséquence arrêtée en attente d'approbation")
    action_id = run["action_id"]
    status, decision = client.request(
        "POST",
        f"/v1/agent/approvals/{action_id}/decision",
        {"approve": False},
        timeout=60,
    )
    if status == 200 and isinstance(decision, dict) and decision.get("status") == "rejected":
        report.ok("Refus honoré — aucune action exécutée (aucun e-mail envoyé)")
    else:
        report.fail("Refus d'approbation non honoré", f"HTTP {status}")


def step_pipeline(
    client: Client, report: Report, brain: bool, skills: set[str], allow_writes: bool
) -> None:
    section("[8] Pipeline commercial — lecture & ajout d'un prospect témoin")
    status, prospects = client.request("GET", "/v1/prospects")
    if status == 200 and isinstance(prospects, list):
        report.ok("Pipeline lisible", f"{len(prospects)} prospect(s) ouvert(s)")
    else:
        report.fail("Pipeline illisible", f"HTTP {status}")
        return

    if not brain:
        report.skip("Ajout d'un prospect témoin", "cerveau non configuré (compétence LLM `add_prospect`)")
        return
    if "add_prospect" not in skills:
        report.skip("Ajout d'un prospect témoin", "compétence pipeline absente")
        return
    if not allow_writes:
        report.skip("Ajout d'un prospect témoin", "--no-writes")
        return

    marker = f"ZZ-SMOKE Prospect {uuid.uuid4().hex[:8]}"
    status, _ = client.request(
        "POST",
        "/v1/agent/runs",
        {"message": f"Ajoute au pipeline un prospect nommé exactement « {marker} »."},
        timeout=90,
    )
    if status != 200:
        report.warn("Ajout d'un prospect témoin", f"HTTP {status} sur /v1/agent/runs")
        return
    _, prospects = client.request("GET", "/v1/prospects")
    hit = next(
        (p for p in prospects if isinstance(p, dict) and marker in p.get("name", "")),
        None,
    ) if isinstance(prospects, list) else None
    if hit is None:
        report.warn(
            "Ajout d'un prospect témoin",
            "le cerveau n'a pas créé le prospect (LLM n'a pas appelé `add_prospect`) — non vérifié",
        )
        return
    report.ok("Prospect témoin ajouté et présent dans le pipeline")
    # Nettoyage : passer le prospect en « perdu » le retire de la liste ouverte.
    client.request(
        "POST",
        "/v1/agent/runs",
        {
            "message": (
                f"Passe le prospect « {marker} » à l'étape perdu "
                f"(son identifiant est {hit.get('prospect_id')})."
            )
        },
        timeout=90,
    )
    _, prospects = client.request("GET", "/v1/prospects")
    still = isinstance(prospects, list) and any(
        isinstance(p, dict) and marker in p.get("name", "") for p in prospects
    )
    if still:
        report.warn(
            "Nettoyage du prospect témoin",
            f"toujours ouvert — retirez manuellement « {marker} » (passer en perdu/gagné)",
        )
    else:
        report.ok("Prospect témoin retiré du pipeline ouvert (nettoyé)")


def step_demo(client: Client, report: Report) -> None:
    section("[9] Démo intégrée — scénarios honnêtes")
    status, scenarios = client.request("GET", "/v1/demo/scenarios")
    if status != 200 or not isinstance(scenarios, list):
        report.fail("Scénarios de démo illisibles", f"HTTP {status}")
        return
    valid = {"live", "assisted", "preview"}
    if all(isinstance(s, dict) and s.get("status") in valid for s in scenarios):
        report.ok("Scénarios de démo cohérents", f"{len(scenarios)} scénario(s)")
    else:
        report.fail("Statut de scénario invalide")
    bizdev = next((s for s in scenarios if s.get("id") == "business_development"), None)
    if bizdev and bizdev.get("status") == "preview":
        report.ok("Honnêteté : découverte de prospects marquée « aperçu » (non simulée)")
    elif bizdev:
        report.warn("Découverte de prospects", f"statut inattendu « {bizdev.get('status')} »")


def cleanup_session(client: Client, report: Report) -> None:
    section("[10] Nettoyage — révocation de la session de test")
    status, _ = client.request("DELETE", "/v1/web/session")
    if status == 204:
        report.ok("Session de test révoquée (place navigateur libérée)")
    else:
        report.warn(
            "Révocation de session",
            f"HTTP {status} — révoquez « ZZ-SMOKE-TEST » manuellement si besoin",
        )


def print_manual(report: Report) -> None:
    section("Reste OBLIGATOIREMENT MANUEL avant de valider le staging")
    for item in (
        "Ouvrir et inspecter un document Word (DOCX) généré : structure, mise en "
        "forme et rendu visuel (aucune vérification automatique du binaire ici).",
        "E-mail réel via Himalaya : envoi approuvé + réception effective sur une "
        "vraie boîte (le smoke-test s'arrête volontairement au REFUS d'envoi).",
        "Chaîne vocale complète : micro → ElevenLabs → Custom LLM → EMEFA, avec "
        "réponse parlée cohérente et contexte métier.",
        "Interruption (barge-in) pendant la réponse vocale + mesure de latence "
        "(temps jusqu'au premier son, latence bout-en-bout).",
    ):
        print(f"  [{MANUAL}] {item}")


def resolve_code(args: argparse.Namespace) -> str | None:
    code = args.enrollment_code or os.environ.get("EMEFA_ENROLLMENT_CODE")
    if code:
        return code
    if sys.stdin.isatty():
        import getpass

        return getpass.getpass("Code d'activation EMEFA (saisie masquée) : ") or None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test de staging EMEFA.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EMEFA_BASE_URL"),
        help="URL de base de l'instance EMEFA (ou variable EMEFA_BASE_URL).",
    )
    parser.add_argument(
        "--enrollment-code",
        help="Code d'activation (ou variable EMEFA_ENROLLMENT_CODE, ou saisie masquée).",
    )
    parser.add_argument(
        "--no-writes",
        action="store_true",
        help="Passage strictement en lecture seule (aucune écriture via le cerveau).",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Timeout HTTP par défaut (s)."
    )
    args = parser.parse_args()

    if not args.base_url:
        print("Erreur : --base-url (ou EMEFA_BASE_URL) est requis.", file=sys.stderr)
        return 2
    code = resolve_code(args)
    if not code:
        print(
            "Erreur : code d'activation requis (--enrollment-code, "
            "EMEFA_ENROLLMENT_CODE, ou terminal interactif).",
            file=sys.stderr,
        )
        return 2

    print(_c("1", f"EMEFA — smoke-test de staging → {args.base_url}"))
    if args.no_writes:
        print(f"  [{INFO}] Mode lecture seule (--no-writes)")

    client = Client(args.base_url, args.timeout)
    report = Report()
    allow_writes = not args.no_writes

    if not step_health(client, report):
        _summary(report)
        return 1 if report.critical_failed else 0
    if not step_activate(client, report, code):
        _summary(report)
        return 1

    try:
        status = step_system(client, report)
        brain = bool(status.get("brain_configured"))
        skills = {
            s.get("name") for s in status.get("skills", []) if isinstance(s, dict)
        }
        step_onboarding(client, report)
        step_memory(client, report, brain, allow_writes)
        step_briefing(client, report)
        step_approvals(client, report, brain, skills, allow_writes)
        step_pipeline(client, report, brain, skills, allow_writes)
        step_demo(client, report)
    finally:
        cleanup_session(client, report)

    print_manual(report)
    return _summary(report)


def _summary(report: Report) -> int:
    section("Bilan")
    print(
        f"  {PASS}: {report.passed}   {FAIL}: {report.failed}   "
        f"{SKIP}: {report.skipped}   {WARN}: {report.warned}"
    )
    if report.critical_failed:
        print(f"\n{_c('31', 'RÉSULTAT : ÉCHEC — au moins une étape critique a échoué.')}")
        return 1
    if report.failed:
        print(f"\n{_c('31', 'RÉSULTAT : ÉCHEC — des étapes non critiques ont échoué.')}")
        return 1
    print(f"\n{_c('32', 'RÉSULTAT : automatisé OK — traiter ensuite les points MANUAL REQUIRED.')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
