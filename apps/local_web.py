"""Explicit app composition for one deterministic local Web target; no model calls."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.activate(("implementation", "requirements"))
import application_spec
import model_review
from domain_checks import CHECKER, check_project
from modelspine_protocols import ArtifactRef, decode, dumps, require
from modelspine_protocols.application import LocalWebSpec
from modelspine_generation.local_web import plan
from modelspine_implementation.local_web import materialize
from modelspine_implementation.local_runtime import decode_local_definition


def load_spec(project_dir):
    """Read A's store, replay the live review, and re-evaluate every readiness gate."""
    current = model_review.read_review(project_dir)
    if current["inspection"]["status"] == "valid":
        decode_local_definition(current["inspection"]["checks"]["candidate"]["definition"])
    saved = application_spec.read_spec(project_dir)
    spec = decode(LocalWebSpec, saved["spec"])
    view = model_review.read_review(project_dir, expected_review_ref=spec.review_ref)
    if view["inspection"]["status"] == "valid":
        decode_local_definition(view["inspection"]["checks"]["candidate"]["definition"])
    result = plan(spec, decode(ArtifactRef, saved["spec_ref"]), view, checker=check_project)
    # Detect a spec-head change during the separate public reads.
    latest = application_spec.read_spec(project_dir)
    require(latest["spec_ref"] == saved["spec_ref"] and latest["assessment"] == result.assessment,
            "spec/review changed during load", "conflict")
    return result


def runtime_sources():
    platform = bootstrap.PLATFORM
    provenance = (platform / "docs/provenance.md").read_text(encoding="utf-8")
    version = subprocess.run(["git", "-c", "safe.directory=" + platform.as_posix(), "-C", str(platform), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
    protocols_version = json.loads((platform / "packages/protocols/module.json").read_text(encoding="utf-8"))["version"]
    mapping = {"domain_checks.py":("apps/domain_checks.py", CHECKER),
               "modelspine_protocols/__init__.py":("packages/protocols/src/modelspine_protocols/__init__.py", "protocols/" + protocols_version),
               "modelspine_protocols/domain_language.py":("packages/protocols/src/modelspine_protocols/domain_language.py", "finite-domain/0.1"),
               "modelspine_protocols/finite_execution.py":("packages/protocols/src/modelspine_protocols/finite_execution.py", "finite-domain/0.2")}
    result = {}
    for target, (source, capability) in mapping.items():
        raw = (platform / source).read_bytes()
        result[target] = {"bytes":raw, "source":source, "sha256":sha256(raw).hexdigest(), "capability":capability,
                          "repository":"https://github.com/Abandooon/ModelSpine.git", "head":version,
                          "identity_note":"working-tree bytes, not an assertion of committed or frozen identity",
                          "license":"platform-wide license not declared", "provenance_notice":provenance}
    return result


def generate(project_dir, output_root, name, *, old_root=None, expected_manifest_hash=None):
    prepared = load_spec(project_dir)
    sources = runtime_sources()
    # Load once again immediately before materialization; there is no cached ready flag.
    require(load_spec(project_dir) == prepared, "review/spec changed before generation", "conflict")
    return materialize(output_root, name, prepared, sources, checker=check_project,
                       old_root=old_root, expected_manifest_hash=expected_manifest_hash)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("load-spec", "generate", "update"))
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--old-root", type=Path)
    parser.add_argument("--expected-manifest-hash")
    args = parser.parse_args(argv)
    try:
        if args.command == "load-spec":
            result = {"status":"generation_ready", "plan":load_spec(args.project_dir)}
        else:
            require(args.output_root is not None and args.name is not None, "explicit output-root and name required")
            require((args.command == "update") == (args.old_root is not None), "update requires old-root; generate forbids it")
            result = generate(args.project_dir, args.output_root, args.name, old_root=args.old_root,
                              expected_manifest_hash=args.expected_manifest_hash)
        print(dumps(result))
        return 0 if result["status"] in ("generated", "generation_ready") else 2
    except (ValueError, OSError, UnicodeError, RecursionError, subprocess.SubprocessError) as exc:
        print(dumps({"status":getattr(exc, "code", "error"), "message":str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
