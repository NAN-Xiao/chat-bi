"""Reference-aware knowledge source file cleanup tests."""

from __future__ import annotations

from types import SimpleNamespace

from apps.knowledge_base.lifecycle_models import KnowledgeBaseVersion
from apps.knowledge_base.source_file_cleanup import cleanup_unreferenced_source_files
from apps.knowledge_base.version_repository import KnowledgeVersionRepository


class _Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Session:
    def __init__(self, *, version_refs=(), legacy_refs=()):
        self.results = [_Rows(version_refs), _Rows(legacy_refs)]

    def exec(self, _statement):
        return self.results.pop(0)


def test_cleanup_deletes_only_unreferenced_files(tmp_path, monkeypatch):
    paths = {name: tmp_path / name for name in ("old.md", "shared.md")}
    for path in paths.values():
        path.write_text(path.name, encoding="utf-8")
    monkeypatch.setattr(
        "apps.knowledge_base.source_file_cleanup.AppFileUtils.get_file_path",
        lambda file_id: str(paths[file_id]),
    )

    result = cleanup_unreferenced_source_files(
        _Session(version_refs=("shared.md",), legacy_refs=()),
        ("old.md", "shared.md"),
    )

    assert result.deleted == ("old.md",)
    assert result.referenced == ("shared.md",)
    assert not paths["old.md"].exists()
    assert paths["shared.md"].exists()


def test_cleanup_reports_missing_files_as_already_clean(tmp_path, monkeypatch):
    missing = tmp_path / "missing.md"
    monkeypatch.setattr(
        "apps.knowledge_base.source_file_cleanup.AppFileUtils.get_file_path",
        lambda _file_id: str(missing),
    )

    result = cleanup_unreferenced_source_files(_Session(), ("missing.md",))

    assert result.missing == ("missing.md",)
    assert result.failed == ()


def test_cleanup_keeps_all_candidates_when_reference_query_fails():
    class _BrokenSession:
        def exec(self, _statement):
            raise RuntimeError("database unavailable")

    result = cleanup_unreferenced_source_files(
        _BrokenSession(),
        ("first.md", "second.md"),
    )

    assert result.failed == ("first.md", "second.md")
    assert result.deleted == ()


def test_cleanup_reports_file_system_failure(tmp_path, monkeypatch):
    directory = tmp_path / "cannot-unlink-as-file"
    directory.mkdir()
    monkeypatch.setattr(
        "apps.knowledge_base.source_file_cleanup.AppFileUtils.get_file_path",
        lambda _file_id: str(directory),
    )

    result = cleanup_unreferenced_source_files(_Session(), ("blocked.md",))

    assert result.failed == ("blocked.md",)
    assert directory.exists()


def test_repository_deletes_publish_jobs_before_versions_and_collects_files():
    class _RepositorySession:
        def __init__(self):
            self.statements = []
            self.deleted_record = None

        def exec(self, statement):
            sql = str(statement)
            self.statements.append(sql)
            if sql.lstrip().startswith("SELECT"):
                return _Rows(("version.md",))
            return SimpleNamespace()

        def add(self, _record):
            return None

        def flush(self):
            return None

        def delete(self, record):
            self.deleted_record = record

    session = _RepositorySession()
    record = SimpleNamespace(
        id=11,
        tenant_id=7,
        file_id="legacy.md",
        draft_version_id=12,
        current_version_id=None,
        publishing_version_id=None,
    )

    result = KnowledgeVersionRepository(session).delete_all(record=record)

    assert result == ("legacy.md", "version.md")
    publish_delete = next(i for i, sql in enumerate(session.statements) if "DELETE FROM knowledge_publish_job" in sql)
    version_delete = next(i for i, sql in enumerate(session.statements) if "DELETE FROM knowledge_base_version" in sql)
    assert publish_delete < version_delete
    assert record.draft_version_id is None
    assert session.deleted_record is record


def test_repository_prunes_oldest_version_after_protecting_live_pointers():
    versions = [
        KnowledgeBaseVersion(
            id=number,
            knowledge_base_id=11,
            tenant_id=7,
            version_number=number,
            status="SUPERSEDED",
            file_id=f"version-{number}.md",
        )
        for number in range(1, 13)
    ]

    class _RepositorySession:
        def __init__(self):
            self.statements = []

        def exec(self, statement):
            self.statements.append(statement)
            sql = str(statement)
            if sql.lstrip().startswith("SELECT") and "knowledge_base_version" in sql:
                return _Rows(tuple(reversed(versions)))
            if sql.lstrip().startswith("SELECT") and "knowledge_publish_job" in sql:
                return _Rows((2,))
            return SimpleNamespace()

        def flush(self):
            return None

    session = _RepositorySession()
    repository = KnowledgeVersionRepository(session)
    repository.lock_knowledge_base = lambda **_kwargs: SimpleNamespace(
        current_version_id=1,
        draft_version_id=12,
        publishing_version_id=None,
    )

    source_file_ids = repository.prune_versions(
        tenant_id=7,
        knowledge_base_id=11,
    )

    assert source_file_ids == ("version-3.md", "version-4.md")
    delete_statements = [
        statement
        for statement in session.statements
        if str(statement).lstrip().startswith("DELETE")
    ]
    assert "DELETE FROM knowledge_publish_job" in str(delete_statements[0])
    assert "DELETE FROM knowledge_base_version" in str(delete_statements[1])
    for statement in delete_statements:
        parameters = statement.compile().params
        assert 11 in parameters.values()
        assert 7 in parameters.values()
        discarded_ids = next(
            value for value in parameters.values() if isinstance(value, list)
        )
        assert set(discarded_ids) == {3, 4}


def test_repository_does_not_query_jobs_when_history_is_within_limit():
    class _RepositorySession:
        def __init__(self):
            self.calls = 0

        def exec(self, _statement):
            self.calls += 1
            return _Rows(
                tuple(
                    KnowledgeBaseVersion(
                        id=number,
                        knowledge_base_id=11,
                        tenant_id=7,
                        version_number=number,
                        status="SUPERSEDED",
                    )
                    for number in range(10, 0, -1)
                )
            )

    session = _RepositorySession()
    repository = KnowledgeVersionRepository(session)
    repository.lock_knowledge_base = lambda **_kwargs: SimpleNamespace()

    assert repository.prune_versions(tenant_id=7, knowledge_base_id=11) == ()
    assert session.calls == 1
