"""Materialize a finite delivery into a new directory; never overwrite an old release."""
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from modelspine_protocols import decode, dumps, require
from modelspine_protocols.domain_language import ProjectModel
from modelspine_generation.local_web import TEMPLATE, render
from .local_runtime import (
    LOCK, MANIFEST, MAX_STORE, directory, entry, exclusive, hash_bytes, no_redirect,
    read_bytes, read_store, safe_path, verify_files, check_target_paths, decode_local_definition,
)

DELIVERY = "local-web-delivery/0.1"
INCOMPLETE = ".incomplete-delivery"
RUN = '''"""Standalone generated entrypoint; no workspace or installation required."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from local_runtime import main
from domain_checks import check_project
if __name__ == "__main__":
    raise SystemExit(main(ROOT, check_project))
'''


def candidate_files(plan, runtime_sources):
    decode_local_definition(plan.definition)
    require(set(runtime_sources) == {"domain_checks.py", "modelspine_protocols/__init__.py", "modelspine_protocols/domain_language.py",
                                    "modelspine_protocols/finite_execution.py"},
            "runtime source set must be explicit and minimal")
    for source in runtime_sources.values():
        require(hash_bytes(source["bytes"]) == source["sha256"], "runtime source bytes/hash mismatch", "conflict")
    files = render(plan)
    files.update({name: source["bytes"] for name, source in runtime_sources.items()})
    files["local_runtime.py"] = Path(__file__).with_name("local_runtime.py").read_bytes()
    files["run.py"] = RUN.encode("utf-8")
    files["SOURCE-NOTICE.txt"] = (
        "ModelSpine finite local application. Platform-wide license not declared.\n"
        "Selected runtime sources are identified in manifest.json; no whole platform or BESSER copied.\n"
        "Upstream provenance record is reproduced below without extending permissions.\n\n"
        + runtime_sources["domain_checks.py"]["provenance_notice"]).encode("utf-8")
    files["RUNNING.txt"] = (
        "Python 3.10+ standard library; no installation.\n"
        "Build: python -B -I run.py build\nLaunch: python -B -I run.py serve\n"
        "Open the exact session URL printed locally. Ctrl+C stops the service.\n"
        "Data path: " + plan.spec["storage"]["relative_path"] + "\n"
        "Keep every saved version; maximum history is 32 MiB, then saves fail without pruning.\n"
        "One local user, one service process; another service/update is refused while locked.\n"
        "Explicit new-directory updates only. Migration/automatic rollback/crash recovery unsupported.\n"
        "A stale .local-web.lock or data .pending requires diagnosis; no automatic stale-lock deletion.\n"
        "This generated app edits/checks/saves/loads only; no domain authorization, remote integration or background business.\n"
    ).encode("utf-8")
    return files


def _paths_do_not_overlap(names):
    names = sorted(x.casefold() for x in names)
    require(len(names) == len(set(names)), "case-insensitive file collision", "conflict")
    require(not any(b.startswith(a + "/") for i, a in enumerate(names) for b in names[i+1:]),
            "file/directory collision", "conflict")


def _snapshot(old_root, expected_manifest_hash):
    require(hash_bytes(read_bytes(old_root / MANIFEST, MAX_STORE)) == expected_manifest_hash,
            "unexpected old manifest hash", "conflict")
    manifest = verify_files(old_root)
    require(not (old_root / INCOMPLETE).exists(), "old delivery incomplete", "incomplete_write")
    expected = {x["path"]:x for x in manifest["files"]}
    actual = {}
    for path in old_root.rglob("*"):
        no_redirect(path)
        if path.is_dir():
            require(any(path.iterdir()), "unmanaged empty directory would be lost: " + path.relative_to(old_root).as_posix(), "conflict")
        if path.is_file():
            name = path.relative_to(old_root).as_posix()
            if name in (MANIFEST, LOCK):
                continue
            require(not name.endswith(".pending"), "unfinished old write", "incomplete_write")
            actual[name] = read_bytes(path, MAX_STORE)
    require(set(expected) <= set(actual), "old owned file missing", "conflict")
    # Every recorded non-data file is a hash precondition, including registered human files.
    for name, item in expected.items():
        if item["owner"] != "data":
            require(hash_bytes(actual[name]) == item["sha256"], "old file changed: " + name, "conflict")
    human = {name: raw for name, raw in actual.items() if name not in expected or expected[name]["owner"] == "human"}
    return manifest, actual, human


def _write_new(output_root, name, plan, runtime_sources, checker, *, old=None, expected_manifest_hash=None):
    output_root = directory(output_root)
    require(name not in (MANIFEST, LOCK, INCOMPLETE), "reserved target name")
    target = safe_path(output_root, name)
    require(not target.exists(), "new output directory already exists", "conflict")
    require(target.parent.is_dir(), "new directory parent must already exist")
    files = candidate_files(plan, runtime_sources)
    data_name = plan.spec["storage"]["relative_path"]
    require(not data_name.casefold().startswith(("modelspine_protocols/",)), "storage overlaps runtime namespace", "conflict")
    data = {"schema_version":"local-project-data/0.1", "project_id":plan.spec["project_id"], "entries":[]}
    definition = decode_local_definition(plan.definition)
    old_manifest, human, actual = None, {}, {}
    if old is not None:
        require(not target.resolve().is_relative_to(old.resolve()) and not old.resolve().is_relative_to(target.resolve()),
                "release directories must be disjoint", "conflict")
        old_manifest, actual, human = _snapshot(old, expected_manifest_hash)
        require(old_manifest["spec_ref"]["project_id"] == plan.spec["project_id"]
                and old_manifest["spec_ref"]["artifact_id"] == plan.spec_ref["artifact_id"], "different application identity", "conflict")
        require(plan.spec_ref != old_manifest["spec_ref"] and plan.spec_ref["revision"] != old_manifest["spec_ref"]["revision"],
                "update needs a new spec version", "conflict")
        require(old_manifest["storage_path"] == data_name, "storage migration unsupported", "unsupported")
        data = read_store(old, data_name, checker, plan.spec["project_id"])
        require(plan.initial_project is None, "update uses retained live data; replacing initial data is unsupported", "unsupported")
        if data["entries"]:
            previous = decode(ProjectModel, data["entries"][-1]["project"])
            # Only the definition binding changes. Objects/links/values/version are never migrated.
            rebound = replace(previous, definition=decode(type(previous.definition), plan.spec["definition_ref"]))
            current = entry(definition, rebound, checker, plan.spec["project_id"], data["entries"][-1]["hash"])
            if current["definition"] != data["entries"][-1]["definition"]:
                data["entries"].append(current)
    elif plan.initial_project is not None:
        data["entries"].append(entry(definition, decode(ProjectModel, plan.initial_project), checker, plan.spec["project_id"], None))
    baseline = data["entries"][-1]["project"] if data["entries"] else None
    used_versions = [item["project"]["version"] for item in data["entries"]]
    check_target_paths(plan.spec, definition, baseline, used_versions, checker)
    files["settings.json"] = dumps({"spec":plan.spec, "definition":plan.definition,
                                    "acceptance_baseline":baseline, "acceptance_used_versions":used_versions}).encode("utf-8")
    require(not any(name in files for name in human), "human file collides with new generated file", "conflict")
    files.update(human)
    _paths_do_not_overlap([*files, data_name, data_name + ".pending", MANIFEST, LOCK, INCOMPLETE])
    for path in (*files, data_name):
        safe_path(target, path)
    raw_data = dumps(data).encode("utf-8")
    require(len(raw_data) <= MAX_STORE, "retained history limit", "unsupported")
    files[data_name] = raw_data
    manifest = {"schema_version":DELIVERY, "target":"python-stdlib-loopback-static", "template":TEMPLATE,
                "input_hash":plan.input_hash, "spec_ref":plan.spec_ref, "spec_content_hash":plan.assessment["spec_content_hash"],
                "bindings":{k:plan.spec[k] for k in ("request_ref", "source_ref", "candidate_ref", "review_ref", "definition_ref", "confirmation_refs")},
                "storage_path":data_name, "previous_manifest_hash":expected_manifest_hash,
                "runtime_sources":{name:{k:v for k,v in source.items() if k not in ("bytes", "provenance_notice")} for name,source in runtime_sources.items()},
                "template_sources":{"local_runtime.py":hash_bytes(files["local_runtime.py"]),
                                    "generator":hash_bytes(Path(sys.modules["modelspine_generation.local_web"].__file__).read_bytes()),
                                    "materializer":hash_bytes(Path(__file__).read_bytes())},
                "files":[{"path":name, "owner":"data" if name == data_name else "human" if name in human else "generated",
                          "sha256":hash_bytes(raw), "expected_old_hash":hash_bytes(actual[name]) if name in actual else None}
                         for name,raw in sorted(files.items())],
                "commands":{"build":["python", "-B", "-I", "run.py", "build"], "launch":["python", "-B", "-I", "run.py", "serve"]},
                "recovery":{"atomic_scope":"single data-file replace; new-directory release", "migration":"unsupported", "rollback":"unsupported", "crash_recovery":"unsupported"}}
    target.mkdir()
    (target / INCOMPLETE).write_text("Build pending; do not serve.\n", encoding="utf-8")
    for name, raw in files.items():
        path = safe_path(target, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    with (target / MANIFEST).open("xb") as stream:
        stream.write(dumps(manifest).encode("utf-8"))
    command = [sys.executable, "-B", "-I", str(target / "run.py"), "build"]
    result = subprocess.run(command, cwd=target, capture_output=True, timeout=60)
    receipt = {"command":command, "cwd":str(target), "exit_code":result.returncode,
               "stdout":result.stdout.decode("utf-8", errors="replace"), "stderr":result.stderr.decode("utf-8", errors="replace")}
    if result.returncode == 0:
        (target / INCOMPLETE).unlink()
    return {"status":"generated" if result.returncode == 0 else "build_failed", "directory":str(target), "build":receipt,
            "manifest_sha256":hash_bytes((target / MANIFEST).read_bytes()), "manifest":manifest}


def materialize(output_root, name, plan, runtime_sources, *, checker, old_root=None, expected_manifest_hash=None):
    if old_root is None:
        require(expected_manifest_hash is None, "old manifest supplied without update")
        return _write_new(output_root, name, plan, runtime_sources, checker)
    require(type(expected_manifest_hash) is str and len(expected_manifest_hash) == 64, "expected old manifest hash required")
    old = directory(old_root)
    with exclusive(old):
        return _write_new(output_root, name, plan, runtime_sources, checker, old=old, expected_manifest_hash=expected_manifest_hash)
