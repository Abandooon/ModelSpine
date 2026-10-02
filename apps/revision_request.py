"""Export an offline revision context from a saved review. No language transport."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_review as review
from modelspine_protocols import ArtifactRef, ContractError, decode, dumps, loads, require
from modelspine_requirements.revision_request import prepare_revision_request, verify_revision_request


def export_revision_request(project_dir, output_path, *, expected_review_ref, action_refs):
    root = review._directory(project_dir)
    output = Path(output_path)
    require(output.is_absolute(), "absolute export path required")
    review._directory(output.parent)
    with review._locked(root):
        result = prepare_revision_request(review._load(root), expected_review_ref=expected_review_ref, action_refs=action_refs)
        raw = dumps(result).encode("utf-8")
        require(len(raw) <= review.MAX_STORE_BYTES, "revision export size limit", "unsupported")
        with output.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(read_revision_request(output) == result, "revision export read-after-write mismatch", "corrupt")
        return result


def read_revision_request(path):
    path = Path(path)
    require(path.is_absolute(), "absolute export path required")
    review._directory(path.parent)
    review._no_redirect(path)
    # loads(dict) preserves strict duplicate/number parsing; nested shape is
    # checked through deterministic replay rather than a second DTO definition.
    data = loads(dict, review._read_bytes(path, review.MAX_STORE_BYTES).decode("utf-8"))
    return verify_revision_request(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "show"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--bindings", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "show":
            result = read_revision_request(args.output)
        else:
            require(args.project_dir is not None and args.bindings is not None, "project and bindings required")
            bindings = loads(dict, review._read_bytes(args.bindings, 65536).decode("utf-8"))
            require(set(bindings) == {"expected_review_ref", "action_refs"}, "invalid export bindings")
            result = export_revision_request(args.project_dir, args.output,
                expected_review_ref=decode(ArtifactRef, bindings["expected_review_ref"]),
                action_refs=tuple(decode(ArtifactRef, r) for r in bindings["action_refs"]))
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
