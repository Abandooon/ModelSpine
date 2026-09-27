"""Prepare raw-text modeling inputs and inspect external candidates; no LLM transport yet."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.activate(("requirements",))

from modelspine_protocols import ArtifactRef, ContractError, dumps, loads, require, to_data
from modelspine_requirements.domain_modeling import (
    MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, MAX_SOURCE_BYTES, ModelingRequest,
    inspect_candidate, modeling_prompt, prepare_request, validate_request,
)
from modelspine_requirements.typed_domain import inspect_typed_candidate, typed_modeling_prompt
from modelspine_protocols.domain_language import ProjectModel
from domain_checks import check_project


def _read(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "input file exceeds contract byte limit", "unsupported")
    return raw


def load_request(path):
    raw = _read(path, MAX_REQUEST_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("invalid", "request must be UTF-8") from exc
    return validate_request(loads(ModelingRequest, text))


def _write(path, text):
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractError("invalid", "output is not representable as UTF-8") from exc
    if path is None:
        sys.stdout.write(text)
    else:
        # Explicit output only; never overwrite a prior request or evidence file.
        with Path(path).open("xb") as stream:
            stream.write(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="pin raw text without any pre-existing model")
    prepare.add_argument("--source", required=True, type=Path)
    prepare.add_argument("--project", required=True)
    prepare.add_argument("--source-id", required=True)
    prepare.add_argument("--source-version", required=True)
    prepare.add_argument("--request-id", required=True)
    prepare.add_argument("--scope", required=True)
    prompt = commands.add_parser("prompt", help="render instructions; does not call a language model")
    prompt.add_argument("--request", required=True, type=Path)
    inspect = commands.add_parser("inspect", help="check a supplied candidate; semantics remain unchecked")
    inspect.add_argument("--request", required=True, type=Path)
    inspect.add_argument("--response", required=True, type=Path)
    typed_prompt = commands.add_parser("typed-prompt", help="source-bound finite language construction instructions")
    typed_prompt.add_argument("--request", type=Path, required=True)
    typed_inspect = commands.add_parser("typed-inspect", help="check finite language candidate and source binding")
    typed_inspect.add_argument("--request", type=Path, required=True)
    typed_inspect.add_argument("--response", type=Path, required=True)
    instance = commands.add_parser("check-project", help="execute finite instance checks; no model writes")
    instance.add_argument("--request", type=Path, required=True)
    instance.add_argument("--response", type=Path, required=True)
    instance.add_argument("--project-model", type=Path, required=True)
    for command in (prepare, prompt, inspect, typed_prompt, typed_inspect, instance):
        command.add_argument("--output", type=Path, help="new UTF-8 file; omitted means stdout")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            raw = _read(args.source, MAX_SOURCE_BYTES)
            reference = ArtifactRef(args.project, args.source_id, args.source_version, sha256(raw).hexdigest())
            request = prepare_request(raw, reference, request_id=args.request_id, scope=args.scope)
            output = dumps(request)
        elif args.command == "prompt":
            output = modeling_prompt(load_request(args.request))
        elif args.command == "typed-prompt":
            output = typed_modeling_prompt(load_request(args.request))
        elif args.command in ("typed-inspect", "check-project"):
            request = load_request(args.request)
            inspection = inspect_typed_candidate(request, _read(args.response, MAX_RESPONSE_BYTES))
            data = {"mode": args.command, "generation_provenance": "not_verified",
                    "model_committed": False, "inspection": to_data(inspection)}
            if args.command == "check-project":
                raw = _read(args.project_model, MAX_RESPONSE_BYTES)
                try:
                    project = loads(ProjectModel, raw.decode("utf-8"))
                except (UnicodeError, RecursionError) as exc:
                    raise ContractError("invalid", "invalid project encoding/nesting") from exc
                data["report"] = to_data(check_project(inspection.candidate.definition, project,
                                                       project_id=request.source.project_id))
            output = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            inspection = inspect_candidate(load_request(args.request), _read(args.response, MAX_RESPONSE_BYTES))
            output = json.dumps({"mode": "external-candidate-inspection",
                                 "generation_provenance": "not_verified",
                                 "model_committed": False,
                                 "inspection": to_data(inspection)}, ensure_ascii=False, indent=2)
        _write(args.output, output)
    except (ContractError, OSError) as exc:
        print(json.dumps({"status": "error", "code": exc.code if isinstance(exc, ContractError) else "io_error",
                          "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
