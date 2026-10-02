"""Local finite review store and CLI. No service, authentication, or language API."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.activate(("requirements",))

from modelspine_protocols import ArtifactRef, ContractError, checked, decode, dumps, loads, require, to_data
from modelspine_protocols.review import ReviewAction, ProjectSubmission, ProposalAdoption
from modelspine_protocols.domain_language import DomainDefinition, ProjectModel
from domain_checks import check_project
from modelspine_requirements.domain_modeling import ModelingRequest
from modelspine_requirements.review import (
    ReviewSession, apply_action, create_session, review_input, review_ref,
)


MAX_STORE_BYTES = 24 * 1024 * 1024
STATE = "model-review.json"
LOCK = ".model-review.lock"
PENDING = ".model-review.pending"


@dataclass(frozen=True)
class _Stored:
    head: ArtifactRef
    session: ReviewSession


def _no_redirect(path):
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
            "review paths must not be symlinks/junctions", "invalid")


def _directory(project_dir):
    root = Path(project_dir)
    require(root.is_absolute(), "explicit absolute project directory required")
    require(root.is_dir(), "project directory must already exist")
    for path in (root, *root.parents):
        _no_redirect(path)
    root = root.resolve(strict=True)
    return root


@contextmanager
def _locked(root):
    try:
        fd = os.open(root / LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ContractError("busy", "review store locked; no automatic stale-lock recovery") from exc
    try:
        os.close(fd)
        # Inspect stable paths only after acquiring the cooperative writer lock.
        # O_EXCL itself rejects an existing lock (including a symlink).
        for name in (STATE, PENDING):
            path = root / name
            if path.exists() or path.is_symlink():
                _no_redirect(path)
                require(path.is_file(), "review store path is not a regular file")
        require(not (root / PENDING).exists(), "incomplete write requires host recovery", "incomplete_write")
        yield
    finally:
        (root / LOCK).unlink()


def _read_bytes(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "review input size limit", "unsupported")
    return raw


def _load(root):
    raw = _read_bytes(root / STATE, MAX_STORE_BYTES)
    try:
        saved = loads(_Stored, raw.decode("utf-8"))
        require(saved.head == review_ref(saved.session), "saved review hash/version mismatch", "conflict")
        review_input(saved.session)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("corrupt", "invalid review store: " + str(exc)) from exc
    return saved.session


def _persist(root, session):
    raw = dumps(_Stored(review_ref(session), session)).encode("utf-8")
    require(len(raw) <= MAX_STORE_BYTES, "review store size limit", "unsupported")
    # Failed writes deliberately leave PENDING for explicit host diagnosis/recovery.
    with (root / PENDING).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(root / PENDING, root / STATE)
    saved = _load(root)
    require(saved == session, "saved review differs after write", "corrupt")


def create_review(project_dir, request: ModelingRequest, candidate_raw: bytes, *, session_id: str) -> dict:
    """Create once in an explicit existing directory, preserving even rejected raw input."""
    session = create_session(request, candidate_raw, session_id=session_id)
    view = review_input(session)
    root = _directory(project_dir)
    with _locked(root):
        if (root / STATE).exists():
            raise FileExistsError("review session already exists")
        _persist(root, session)
    return view


def read_review(project_dir, *, expected_review_ref: ArtifactRef | None = None) -> dict:
    root = _directory(project_dir)
    with _locked(root):
        session = _load(root)
        if expected_review_ref is not None:
            require(review_ref(session) == expected_review_ref, "unexpected saved review version", "conflict")
        return review_input(session)


def _definition(view):
    require(view["inspection"]["status"] == "valid", "invalid candidate cannot execute")
    return decode(DomainDefinition, view["inspection"]["checks"]["candidate"]["definition"])


def _submit(project_dir, action) -> dict:
    root = _directory(project_dir)
    with _locked(root):
        session = _load(root)
        successor, receipt = apply_action(session, action)
        if successor != session:
            if isinstance(action, ProjectSubmission):
                # Structural validity belongs to the actual checker. Violated/unknown
                # outcomes are legitimate stored examples, not save failures.
                view = review_input(session)
                check_project(_definition(view), action.project, project_id=view["project_id"])
            _persist(root, successor)
    return receipt


def submit_action(project_dir, action: ReviewAction) -> dict:
    return _submit(project_dir, checked(action, ReviewAction))


def save_project(project_dir, submission: ProjectSubmission) -> dict:
    return _submit(project_dir, checked(submission, ProjectSubmission))


def adopt_proposal(project_dir, adoption: ProposalAdoption) -> dict:
    return _submit(project_dir, checked(adoption, ProposalAdoption))


def _project_entry(view, project_ref, expected_review_ref):
    require(to_data(expected_review_ref) == view["review_ref"], "stale review for instance read/check", "conflict")
    for snapshot in (view, *(item["view"] for item in view["history"])):
        for entry in snapshot["projects"]:
            if entry["ref"] == to_data(project_ref):
                return entry
    raise ContractError("conflict", "project reference does not belong to this review")


def read_project(project_dir, project_ref: ArtifactRef, *, expected_review_ref: ArtifactRef) -> dict:
    root = _directory(project_dir)
    with _locked(root):
        return _project_entry(review_input(_load(root)), project_ref, expected_review_ref)


def check_saved_project(project_dir, project_ref: ArtifactRef, *, expected_review_ref: ArtifactRef) -> dict:
    root = _directory(project_dir)
    with _locked(root):
        view = review_input(_load(root))
        entry = _project_entry(view, project_ref, expected_review_ref)
        require(entry["candidate_ref"] == view["candidate_ref"] and entry["request_ref"] == view["request_ref"]
                and entry["definition_ref"] == view["definition_ref"], "instance belongs to an archived candidate", "conflict")
        definition = _definition(view)
        project = decode(ProjectModel, entry["project"])
        report = check_project(definition, project, project_id=view["project_id"])
        return {"status": "checked", "project_ref": entry["ref"], "purpose": entry["purpose"],
                "request_ref": view["request_ref"], "candidate_ref": view["candidate_ref"],
                "definition_ref": view["definition_ref"], "review_ref": view["review_ref"],
                "population_complete": project.population_complete,
                "required_residuals": [r.id for r in definition.residuals if r.required], "report": to_data(report)}


def engineering_demo(project_dir) -> dict:
    """Hand-authored engineering fixture; never an automatic language result."""
    from modelspine_protocols import decode, digest
    from modelspine_requirements.domain_modeling import prepare_request
    raw = "设备有就绪标记并连接部件；可运行条件及数量仍需用户说明。".encode("utf-8")
    request = prepare_request(raw, ArtifactRef("engineering-review", "source", "1", sha256(raw).hexdigest()),
                              request_id="request", scope="engineering review only")
    span = {"start_line": 1, "end_line": 1, "quote": request.text}
    literal = lambda value: {"op": "literal", "args": [], "symbol": None, "value": value}
    definition = {"schema_version": "finite-domain/0.1", "id": "engineering", "version": "1",
                  "entities": [{"id": "device", "name": "设备", "fields": [
                      {"id": "ready", "name": "就绪", "value_type": "boolean", "required": True, "nullable": False}]},
                      {"id": "part", "name": "部件", "fields": []}],
                  "relations": [{"id": "uses", "name": "连接", "source": "device", "target": "part",
                                 "targets_per_source": {"minimum": 0, "maximum": "unbounded"},
                                 "sources_per_target": {"minimum": 0, "maximum": "unbounded"}}],
                  "constraints": [{"id": "ready-rule", "context": "device", "applies": literal(True),
                                   "assertion": {"op": "field", "args": [], "symbol": "ready", "value": None},
                                   "unless": literal(False)}],
                  "residuals": [{"id": "open-count", "family": "cardinality", "text": "数量待澄清", "required": True}]}
    candidate = {"schema_version": "typed-domain-candidate/0.1", "request_hash": digest(request),
                 "status": "unconfirmed", "definition": definition,
                 "traces": [{"element": name, "evidence": [span]} for name in
                            ("device", "ready", "part", "uses", "ready-rule", "open-count")],
                 "issues": [{"id": "q-count", "kind": "missing_information", "text": "数量待澄清",
                             "related_ids": ["open-count"], "question": "需要多少部件？", "evidence": [span]}]}
    view = create_review(project_dir, request, dumps(candidate).encode("utf-8"), session_id="review-demo")
    action = ReviewAction("model-review/0.1", "answer-1", view["project_id"],
                          decode(ArtifactRef, view["request_ref"]), decode(ArtifactRef, view["candidate_ref"]),
                          decode(ArtifactRef, view["review_ref"]), decode(ArtifactRef, view["questions"][0]["ref"]),
                          "engineering-actor", "answer", "尚不确定，暂不补默认数量", (), None)
    receipt = submit_action(project_dir, action)
    return {"provenance": "hand_authored_engineering_only", "receipt": receipt,
            "reopened": read_review(project_dir), "language_api_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "show", "act", "demo", "save-project", "read-project", "check-project", "adopt"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--project-dir", required=True, type=Path)
        if name == "create":
            cmd.add_argument("--request", type=Path, required=True)
            cmd.add_argument("--candidate", type=Path, required=True)
            cmd.add_argument("--session-id", required=True)
        if name == "act":
            cmd.add_argument("--action", type=Path, required=True)
        if name == "save-project":
            cmd.add_argument("--submission", type=Path, required=True)
        if name == "adopt":
            cmd.add_argument("--adoption", type=Path, required=True)
        if name in ("read-project", "check-project"):
            cmd.add_argument("--project-ref", type=Path, required=True)
            cmd.add_argument("--expected-review-ref", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            request = loads(ModelingRequest, _read_bytes(args.request, 512 * 1024).decode("utf-8"))
            output = create_review(args.project_dir, request, _read_bytes(args.candidate, 256 * 1024),
                                   session_id=args.session_id)
        elif args.command == "show":
            output = read_review(args.project_dir)
        elif args.command == "act":
            action = loads(ReviewAction, _read_bytes(args.action, 512 * 1024).decode("utf-8"))
            output = submit_action(args.project_dir, action)
        elif args.command == "save-project":
            output = save_project(args.project_dir, loads(ProjectSubmission, _read_bytes(args.submission, 512 * 1024).decode("utf-8")))
        elif args.command == "adopt":
            output = adopt_proposal(args.project_dir, loads(ProposalAdoption, _read_bytes(args.adoption, 512 * 1024).decode("utf-8")))
        elif args.command in ("read-project", "check-project"):
            project_ref = loads(ArtifactRef, _read_bytes(args.project_ref, 64 * 1024).decode("utf-8"))
            expected = loads(ArtifactRef, _read_bytes(args.expected_review_ref, 64 * 1024).decode("utf-8"))
            output = (read_project if args.command == "read-project" else check_saved_project)(
                args.project_dir, project_ref, expected_review_ref=expected)
        else:
            output = engineering_demo(args.project_dir)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RecursionError) as exc:
        print(json.dumps({"status": "error", "code": exc.code if isinstance(exc, ContractError) else "input_or_io_error",
                          "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
