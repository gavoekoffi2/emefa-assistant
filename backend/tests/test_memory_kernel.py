"""Memory kernel behaviour (ADR-003).

These tests pin the properties that make the kernel worth having over a flat
list: restating a fact must not duplicate it, changing a fact must not destroy
the previous one, and ranking must be salience rather than recency.
"""

from datetime import datetime, timedelta, timezone

import pytest

from emefa.domain import storage
from emefa.domain.memories import MemoryRepository
from emefa.domain.memory import vocabulary
from emefa.domain.memory.kernel import MemoryKernel, _fts_query
from emefa.domain.memory.retrieval import MemoryRetrieval
from emefa.domain.memory.schemas import DecayPolicy, FactStatus


def test_restating_a_fact_reinforces_instead_of_duplicating(tmp_path):
    repository = MemoryRepository(tmp_path / "reinforce.db")
    first, outcome = repository.record_fact(
        "utilisateur", "propose", "des panneaux solaires", "offer"
    )
    assert outcome == "created"
    again, outcome = repository.record_fact(
        "Utilisateur", "propose", "  des   panneaux solaires ", "offer"
    )
    assert outcome == "reinforced"
    assert again.fact_id == first.fact_id
    assert again.support_count == 2
    assert again.confidence > first.confidence
    assert repository.kernel.count_facts(FactStatus.ACTIVE) == 1


def test_changing_a_fact_supersedes_the_old_one_without_deleting_it(tmp_path):
    repository = MemoryRepository(tmp_path / "supersede.db")
    old, _ = repository.record_fact("utilisateur", "souhaite", "ouvrir à Accra", "goal")
    new, outcome = repository.record_fact(
        "utilisateur", "souhaite", "ouvrir à Abidjan", "goal"
    )
    assert outcome == "superseded"

    replaced = repository.kernel.get_fact(old.fact_id)
    assert replaced is not None, "a contradicted fact must never be deleted"
    assert replaced.status is FactStatus.SUPERSEDED
    assert [fact.fact_id for fact in repository.kernel.superseded_by(new.fact_id)] == [
        old.fact_id
    ]
    # Only the current belief is active, but the history stays answerable.
    assert [memory.content for memory in repository.list_all()] == [
        "utilisateur souhaite ouvrir à Abidjan"
    ]
    history = repository.history(new.fact_id)
    assert history["replaced"][0]["content"] == "utilisateur souhaite ouvrir à Accra"


def test_notes_in_the_same_category_coexist(tmp_path):
    """Unstructured notes carry no claim another note could contradict."""
    repository = MemoryRepository(tmp_path / "notes.db")
    repository.remember("Le fournisseur livre le mardi", "fact")
    repository.remember("La banque ferme à 15h", "fact")
    assert len(repository.list_all()) == 2


def test_an_identical_note_is_recorded_once_and_reinforced(tmp_path):
    repository = MemoryRepository(tmp_path / "dup.db")
    first = repository.remember("Le comptable s'appelle Ama", "relationship")
    second = repository.remember("  le COMPTABLE s'appelle Ama  ", "relationship")
    assert second.memory_id == first.memory_id
    assert len(repository.list_all()) == 1
    assert repository.history(first.memory_id)["support_count"] == 2


def test_human_correction_rewrites_in_place_and_raises_confidence(tmp_path):
    repository = MemoryRepository(tmp_path / "correct.db")
    saved = repository.remember("Le comptable s'appelle Amma", "relationship")
    corrected = repository.correct(saved.memory_id, "Le comptable s'appelle Ama")
    assert corrected.content == "Le comptable s'appelle Ama"
    assert repository.history(saved.memory_id)["confidence"] > 0.9
    # The correction is searchable under the new spelling, not the old one.
    assert repository.search("Ama")
    assert repository.correct("absent", "peu importe") is None
    with pytest.raises(ValueError):
        repository.correct(saved.memory_id, "   ")


def test_forget_is_the_only_path_that_removes_rows(tmp_path):
    repository = MemoryRepository(tmp_path / "forget.db")
    saved = repository.remember("À oublier", "other")
    assert repository.forget(saved.memory_id) is True
    assert repository.forget(saved.memory_id) is False
    assert repository.kernel.get_fact(saved.memory_id) is None
    assert repository.kernel.search("oublier") == []
    # The originating event survives: it records the conversation, not the belief.
    assert repository.kernel.count_events() >= 1


def test_decay_ranks_a_stale_commitment_below_a_durable_identity(tmp_path):
    kernel = MemoryKernel(tmp_path / "decay.db")
    kernel.insert_fact("utilisateur", "s_appelle", "Koffi", "identity")
    kernel.insert_fact(
        "utilisateur", "a_pour_echeance", "livrer le rapport", "commitment"
    )
    retrieval = MemoryRetrieval(kernel)

    fresh = retrieval.retrieve("Koffi rapport", limit=2)
    later = retrieval.retrieve(
        "Koffi rapport", limit=2, now=datetime.now(timezone.utc) + timedelta(days=120)
    )

    def score_of(results, category):
        return next(item.score for item in results if item.fact.category == category)

    # Four months on, the identity is untouched and the commitment has faded.
    assert score_of(later, "identity") == pytest.approx(score_of(fresh, "identity"))
    assert score_of(later, "commitment") < score_of(fresh, "commitment") * 0.1
    assert later[0].fact.category == "identity"


def test_relevance_beats_recency(tmp_path):
    """The failure the flat store had: the newest row always won."""
    repository = MemoryRepository(tmp_path / "rank.db")
    repository.record_fact(
        "utilisateur", "propose", "installation de panneaux solaires", "offer"
    )
    for index in range(10):
        repository.remember(f"Note sans rapport numéro {index}", "other")

    ranked = repository.retrieval.retrieve("panneaux solaires", limit=3)
    assert "panneaux" in ranked[0].fact.object


def test_context_block_stays_bounded_and_mentions_what_changed(tmp_path):
    repository = MemoryRepository(tmp_path / "ctx.db")
    repository.record_fact("utilisateur", "souhaite", "ouvrir à Accra", "goal")
    repository.record_fact("utilisateur", "souhaite", "ouvrir à Abidjan", "goal")
    block = repository.context_block(max_items=5, query="ouvrir")
    assert block.startswith("Mémoire durable")
    assert "Abidjan" in block
    assert "auparavant : ouvrir à Accra" in block


def test_search_survives_punctuation_and_operators(tmp_path):
    """Voice transcripts and chat boxes send FTS5 operators as ordinary text."""
    repository = MemoryRepository(tmp_path / "fts.db")
    repository.remember("Le marché cible est à Lomé", "market")

    # Operator soup must return a result set, not raise, and not match wildly.
    assert isinstance(repository.kernel.search('"OR" NEAR* ('), list)
    assert repository.kernel.search("???") == []
    # Accents are folded, so the unaccented spelling still finds the fact.
    assert any("Lomé" in memory.content for memory in repository.search("lome"))


def test_fts_query_cannot_express_an_operator():
    # Quotes, colons and the OR operator all come back as quoted literals or
    # are dropped as too short to be worth matching.
    assert _fts_query('panneaux" OR fact_id:*') == '"panneaux" OR "fact"'
    assert _fts_query("!!! ??") == ""


def test_unknown_vocabulary_is_coerced_not_rejected(tmp_path):
    repository = MemoryRepository(tmp_path / "vocab.db")
    fact, _ = repository.record_fact(
        "utilisateur", "a une préférence marquée pour", "les appels courts", "inventée"
    )
    assert fact.category == "other"
    assert fact.predicate in vocabulary.PREDICATES
    assert fact.decay_policy is DecayPolicy.MEDIUM


def test_legacy_memories_are_migrated_into_facts(tmp_path):
    """Upgrading an existing instance must not lose a single memory."""
    database = tmp_path / "legacy.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    with storage.connect(database) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP)"
        )
        for version, statements in enumerate(storage.MIGRATIONS[:9], start=1):
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
        connection.execute(
            "INSERT INTO memories (memory_id, category, content, source) "
            "VALUES ('mem_ancien', 'preference', 'Réunions le matin', 'conversation')"
        )
    assert storage.schema_version(database) == 9

    repository = MemoryRepository(database)

    assert storage.schema_version(database) == 16
    migrated = repository.get("mem_ancien")
    assert migrated is not None, "existing memory ids must keep resolving"
    assert migrated.content == "Réunions le matin"
    assert migrated.category == "preference"
    assert migrated.source == "conversation"
    assert repository.search("réunions")
    # The old table is kept under an archive name as the rollback path.
    with storage.connect(database) as connection:
        archived = connection.execute(
            "SELECT COUNT(*) FROM memories_v1_archive"
        ).fetchone()[0]
    assert archived == 1


@pytest.mark.asyncio
async def test_memory_api_exposes_history_search_and_correction(tmp_path):
    """The user must be able to inspect, correct and delete what EMEFA
    believes about them (CLAUDE.md §26)."""
    import httpx

    from emefa.config import Settings
    from emefa.domain.agent import AgentStep
    from emefa.main import create_app

    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    database = tmp_path / "api.db"
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=database,
            cookie_secure=False,
        ),
        brain=Brain(),
    )
    repository = MemoryRepository(database)
    repository.record_fact("utilisateur", "souhaite", "ouvrir à Accra", "goal")
    current, _ = repository.record_fact("utilisateur", "souhaite", "ouvrir à Abidjan", "goal")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/memories/stats")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )

        stats = (await web.get("/v1/memories/stats")).json()
        assert stats == {"events": 0, "active_facts": 1, "superseded_facts": 1}

        found = (await web.get("/v1/memories/search", params={"q": "abidjan"})).json()
        assert any("Abidjan" in item["content"] for item in found)

        history = (await web.get(f"/v1/memories/{current.fact_id}/history")).json()
        assert history["replaced"][0]["content"] == "utilisateur souhaite ouvrir à Accra"
        assert (await web.get("/v1/memories/absent/history")).status_code == 404

        patched = await web.patch(
            f"/v1/memories/{current.fact_id}", json={"content": "ouvrir à Abidjan en mars"}
        )
        assert patched.status_code == 200
        assert patched.json()["content"] == "utilisateur souhaite ouvrir à Abidjan en mars"
        assert (
            await web.patch("/v1/memories/absent", json={"content": "peu importe"})
        ).status_code == 404


def test_memory_skills_cover_recall_correction_and_history(tmp_path):
    from emefa.domain.policy import ActionRisk
    from emefa.domain.profiles import ProfileRepository
    from emefa.skills import build_tool_shelf

    database = tmp_path / "shelf.db"
    memories = MemoryRepository(database)
    shelf = build_tool_shelf(ProfileRepository(database), memories=memories)

    saved = shelf.get("remember").handler(
        {"content": "Le fournisseur livre le mardi", "category": "procedure"}
    )["memory"]

    assert shelf.get("recall").risk is ActionRisk.PERSONAL_READ
    assert shelf.get("recall").handler({"query": "fournisseur"})["count"] >= 1
    assert shelf.get("recall").handler({"query": "a"})["error"] == "query_too_short"

    corrected = shelf.get("correct_memory").handler(
        {"memory_id": saved["memory_id"], "content": "Le fournisseur livre le mercredi"}
    )
    assert corrected["memory"]["content"] == "Le fournisseur livre le mercredi"
    assert (
        shelf.get("correct_memory").handler({"memory_id": "absent", "content": "abc"})["error"]
        == "memory_not_found"
    )

    history = shelf.get("memory_history").handler({"memory_id": saved["memory_id"]})
    assert history["support_count"] == 1
    assert [item["type"] for item in history["observations"]] == ["created", "corrected"]
