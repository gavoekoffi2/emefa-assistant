"""A live instance must upgrade in place without losing anything.

The deployed database sits at schema 10. Migrations 11-15 add executive
profile depth, the CRM, meetings, the artifact catalogue and the evening
report. This test builds a realistic v10 database, upgrades it, and asserts
both halves of the contract: nothing existing is lost, and everything new
works on the upgraded file.
"""

import pytest

from emefa.domain import storage
from emefa.domain.crm import CrmRepository
from emefa.domain.documents import DocumentStore
from emefa.domain.memories import MemoryRepository
from emefa.domain.office import DocumentSpec, PythonOfficeProvider, parse_content
from emefa.domain.onboarding import OnboardingRepository
from emefa.domain.profiles import ProfileRepository
from emefa.domain.prospects import ProspectRepository
from emefa.domain.tasks import TaskRepository

PREVIOUS_SHIPPED_VERSION = 10


@pytest.fixture
def legacy_database(tmp_path, monkeypatch):
    """A database at the previously shipped schema version, with real data."""
    database = tmp_path / "emefa.db"
    monkeypatch.setattr(storage, "MIGRATIONS", storage.MIGRATIONS[:PREVIOUS_SHIPPED_VERSION])
    storage.run_migrations(database)
    assert storage.schema_version(database) == PREVIOUS_SHIPPED_VERSION
    with storage.connect(database) as connection:
        connection.execute("INSERT INTO tasks (task_id, title) VALUES ('t1', 'Tâche existante')")
        connection.execute(
            "UPDATE business_profiles SET company_name = 'Horizon SARL', goals = 'Grandir'"
        )
        connection.execute(
            "INSERT INTO memories (memory_id, content) VALUES ('m1', 'Préfère le tutoiement')"
        )
        connection.execute(
            "INSERT INTO prospects (prospect_id, name) VALUES ('p1', 'Ancien prospect')"
        )
    monkeypatch.undo()
    return database


def test_upgrade_preserves_existing_data_and_enables_the_new_capabilities(legacy_database):
    storage.run_migrations(legacy_database)
    assert storage.schema_version(legacy_database) == len(storage.MIGRATIONS)

    profile = ProfileRepository(legacy_database).get_business()
    assert profile.company_name == "Horizon SARL"
    assert profile.goals == "Grandir"
    # New columns arrive empty rather than breaking the row.
    assert profile.preferred_name == ""
    assert profile.autonomy_level == ""

    assert [task.title for task in TaskRepository(legacy_database).list_open()] == ["Tâche existante"]
    assert [m.content for m in MemoryRepository(legacy_database).list_all()] == ["Préfère le tutoiement"]
    assert [p.name for p in ProspectRepository(legacy_database).list_open()] == ["Ancien prospect"]

    crm = CrmRepository(legacy_database)
    crm.save_contact(name="Nouveau client", kind="client")
    assert len(crm.list_contacts()) == 1

    onboarding = OnboardingRepository(legacy_database, ProfileRepository(legacy_database))
    status = onboarding.status()
    # The company name already known counts as progress, so it is never re-asked.
    entreprise = next(t for t in status["topics"] if t["topic_id"] == "entreprise")
    assert "company_name" in [item["field"] for item in entreprise["known_fields"]]


def test_documents_written_before_the_catalogue_are_adopted(legacy_database):
    """Artifacts on disk from the previous release must not disappear."""
    root = legacy_database.parent / "documents"
    root.mkdir(exist_ok=True)
    legacy_id = "11111111-2222-3333-4444-555555555555"
    PythonOfficeProvider().render_document(
        DocumentSpec(title="Ancien rapport", blocks=parse_content("Contenu hérité")),
        root / f"{legacy_id}.docx",
    )

    storage.run_migrations(legacy_database)
    listed = DocumentStore(legacy_database).list()

    assert [item["title"] for item in listed] == ["Ancien rapport"]
    assert listed[0]["document_id"] == legacy_id
    assert listed[0]["kind"] == "document"
    assert listed[0]["filename"] == "Ancien-rapport.docx"
