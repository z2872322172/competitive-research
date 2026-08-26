from pathlib import Path

from scripts.cleanup_dev_artifacts import cleanup_artifacts, collect_artifacts


def test_collect_artifacts_reports_known_local_files(tmp_path: Path):
    (tmp_path / "verda_dev.db").write_text("sqlite", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "uvicorn.log").write_text("log", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "dist").mkdir()
    (tmp_path / "README.md").write_text("keep", encoding="utf-8")

    artifacts = collect_artifacts(tmp_path)

    relative_paths = {artifact.relative_path for artifact in artifacts}
    assert relative_paths == {
        "verda_dev.db",
        "backend/uvicorn.log",
        "frontend/dist",
    }


def test_cleanup_artifacts_dry_run_does_not_delete_files(tmp_path: Path):
    database = tmp_path / "verda_dev.db"
    database.write_text("sqlite", encoding="utf-8")

    result = cleanup_artifacts(tmp_path)

    assert result.apply is False
    assert result.deleted == []
    assert result.failed == []
    assert [artifact.relative_path for artifact in result.found] == ["verda_dev.db"]
    assert database.exists()


def test_cleanup_artifacts_apply_deletes_known_artifacts(tmp_path: Path):
    database = tmp_path / "verda_dev.db"
    cache_dir = tmp_path / ".pytest_cache"
    database.write_text("sqlite", encoding="utf-8")
    cache_dir.mkdir()
    (cache_dir / "README.md").write_text("cache", encoding="utf-8")

    result = cleanup_artifacts(tmp_path, apply=True)

    assert result.apply is True
    assert result.failed == []
    assert result.deleted == [".pytest_cache", "verda_dev.db"]
    assert not database.exists()
    assert not cache_dir.exists()

