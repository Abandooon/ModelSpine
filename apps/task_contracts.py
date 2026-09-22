"""Read only the task/source paths explicitly supplied by the caller."""
from pathlib import Path
from collections.abc import Mapping

from modelspine_assurance.tasks import PreparedTask, prepare_task
from modelspine_protocols import ArtifactRef, ContractError


def load_task(path: Path, expected_task_ref: ArtifactRef,
              source_paths: Mapping[ArtifactRef, Path]) -> PreparedTask:
    try:
        raw = path.read_bytes()
        sources = {reference: source.read_bytes() for reference, source in source_paths.items()}
    except OSError as exc:
        raise ContractError("not_found", f"task/source file unreadable: {exc}") from exc
    return prepare_task(raw, expected_task_ref, sources)
