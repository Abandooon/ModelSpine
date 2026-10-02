"""Local bounded application-spec drafts; no generator or network calls."""
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_review as review
from domain_checks import check_project
from modelspine_protocols import ArtifactRef, ContractError, digest, dumps, loads, require, to_data
from modelspine_protocols.application import LocalWebSpec, assess_application, validate_spec

STATE = "application-spec.json"
PENDING = ".application-spec.pending"


@dataclass(frozen=True)
class SpecEntry:
    ref: ArtifactRef
    parent_ref: ArtifactRef | None
    spec: LocalWebSpec


@dataclass(frozen=True)
class SpecStore:
    entries: tuple[SpecEntry, ...]


def _paths(root):
    for name in (STATE, PENDING):
        path = root / name
        if path.exists() or path.is_symlink():
            review._no_redirect(path)
            require(path.is_file(), "spec path must be regular file")
    require(not (root / PENDING).exists(), "incomplete spec write requires recovery", "incomplete_write")


def _ref(spec):
    return ArtifactRef(spec.project_id, "application/" + spec.id, spec.version, digest(spec))


def _load(root):
    try:
        store = loads(SpecStore, review._read_bytes(root / STATE, review.MAX_STORE_BYTES).decode("utf-8"))
        require(0 < len(store.entries) <= 32, "invalid spec history length")
        previous = None
        versions = set()
        identity = (store.entries[0].spec.project_id, store.entries[0].spec.id)
        for entry in store.entries:
            validate_spec(entry.spec)
            require(entry.ref == _ref(entry.spec) and entry.parent_ref == previous, "spec version/hash chain mismatch")
            require((entry.spec.project_id, entry.spec.id) == identity and entry.spec.version not in versions,
                    "spec identity/version mismatch")
            versions.add(entry.spec.version)
            previous = entry.ref
        return store
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("corrupt", "invalid application-spec store") from exc


def _result(store, view):
    current = store.entries[-1]
    return {"spec_ref": to_data(current.ref), "spec": to_data(current.spec),
            "history_refs": [to_data(x.ref) for x in store.entries[:-1]],
            "assessment": assess_application(current.spec, view, checker=check_project)}


def save_spec(project_dir, spec: LocalWebSpec, *, expected_spec_ref: ArtifactRef | None = None):
    spec = validate_spec(spec)
    root = review._directory(project_dir)
    with review._locked(root):
        _paths(root)
        view = review.review_input(review._load(root))
        for key in ("project_id", "request_ref", "source_ref", "candidate_ref", "definition_ref", "review_ref"):
            require(to_data(getattr(spec, key)) == view[key], "spec live binding mismatch: " + key, "conflict")
        previous = _load(root) if (root / STATE).exists() else SpecStore(())
        if previous.entries and previous.entries[-1].spec == spec:
            return {"status": "already_recorded", **_result(previous, view)}
        head = previous.entries[-1].ref if previous.entries else None
        require(expected_spec_ref == head, "stale application-spec head", "conflict")
        require(len(previous.entries) < 32, "spec history limit", "unsupported")
        if previous.entries:
            require(spec.id == previous.entries[-1].spec.id and spec.project_id == previous.entries[-1].spec.project_id,
                    "spec identity changed", "conflict")
            require(spec.version not in {x.spec.version for x in previous.entries}, "spec version already used", "conflict")
        current = SpecStore(previous.entries + (SpecEntry(_ref(spec), head, spec),))
        result = _result(current, view)  # Evaluate readiness; draft is still saveable.
        raw = dumps(current).encode("utf-8")
        require(len(raw) <= review.MAX_STORE_BYTES, "spec store size limit", "unsupported")
        with (root / PENDING).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(root / PENDING, root / STATE)
        require(_load(root) == current, "spec read-after-write mismatch", "corrupt")
        return {"status": "recorded", **result}


def read_spec(project_dir):
    root = review._directory(project_dir)
    with review._locked(root):
        _paths(root)
        return _result(_load(root), review.review_input(review._load(root)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("save", "show"))
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--expected-spec-ref", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "show":
            result = read_spec(args.project_dir)
        else:
            require(args.spec is not None, "--spec required")
            spec = loads(LocalWebSpec, review._read_bytes(args.spec, 2 * 1024 * 1024).decode("utf-8"))
            expected = (loads(ArtifactRef, review._read_bytes(args.expected_spec_ref, 65536).decode("utf-8"))
                        if args.expected_spec_ref else None)
            result = save_spec(args.project_dir, spec, expected_spec_ref=expected)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RecursionError) as exc:
        print(json.dumps({"status": "error", "code": exc.code if isinstance(exc, ContractError) else "input_or_io_error",
                          "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
