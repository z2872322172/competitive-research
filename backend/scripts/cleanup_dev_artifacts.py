from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ARTIFACT_PATTERNS = (
    ".pytest_cache",
    "verda_dev.db",
    "backend/.pytest_cache",
    "backend/verda_dev.db",
    "backend/verda_stage3_smoke.db",
    "backend/*.log",
    "frontend/*.log",
    "frontend/dist",
)


@dataclass(frozen=True)
class Artifact:
    path: Path
    relative_path: str
    kind: str


@dataclass(frozen=True)
class CleanupResult:
    apply: bool
    found: list[Artifact]
    deleted: list[str]
    failed: list[str]


def _normalize_relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _artifact_for(path: Path, root: Path) -> Artifact:
    kind = "directory" if path.is_dir() else "file"
    return Artifact(path=path, relative_path=_normalize_relative_path(path, root), kind=kind)


def collect_artifacts(root: Path, patterns: tuple[str, ...] = DEFAULT_ARTIFACT_PATTERNS) -> list[Artifact]:
    resolved_root = root.resolve()
    artifacts: dict[str, Artifact] = {}

    for pattern in patterns:
        for path in resolved_root.glob(pattern):
            if not path.exists():
                continue
            resolved_path = path.resolve()
            if resolved_path == resolved_root or not resolved_path.is_relative_to(resolved_root):
                continue
            artifact = _artifact_for(resolved_path, resolved_root)
            artifacts[artifact.relative_path] = artifact

    return [artifacts[key] for key in sorted(artifacts)]


def cleanup_artifacts(root: Path, apply: bool = False) -> CleanupResult:
    artifacts = collect_artifacts(root)
    deleted: list[str] = []
    failed: list[str] = []

    if apply:
        for artifact in artifacts:
            try:
                if artifact.path.is_dir():
                    shutil.rmtree(artifact.path)
                else:
                    artifact.path.unlink()
                deleted.append(artifact.relative_path)
            except OSError:
                failed.append(artifact.relative_path)

    return CleanupResult(apply=apply, found=artifacts, deleted=deleted, failed=failed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory or remove local development artifacts.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="Project root to scan.")
    parser.add_argument("--apply", action="store_true", help="Delete found artifacts. Without this flag, only list them.")
    args = parser.parse_args()

    result = cleanup_artifacts(args.root, apply=args.apply)
    action = "deleted" if result.apply else "found"
    for artifact in result.found:
        print(f"{action}: {artifact.relative_path} ({artifact.kind})")
    for relative_path in result.failed:
        print(f"failed: {relative_path}")

    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

