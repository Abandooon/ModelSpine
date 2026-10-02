"""Finite local service runtime. Checker injected by the explicit application host."""
import argparse
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import sys
import threading

from modelspine_protocols import ContractError, decode, digest, dumps, loads, require, to_data
from modelspine_protocols.domain_language import DomainDefinition, ProjectModel

MAX_REQUEST = 2 * 1024 * 1024
MAX_STORE = 32 * 1024 * 1024
LOCK = ".local-web.lock"
MANIFEST = "manifest.json"


def hash_bytes(raw):
    return sha256(raw).hexdigest()


def no_redirect(path):
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
            "symlink/junction forbidden", "conflict")
    require(not path.is_file() or info.st_nlink == 1, "hard-linked file forbidden", "conflict")


def directory(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "explicit absolute directory required")
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            no_redirect(parent)
    require(path.is_dir(), "directory does not exist")
    return path


def safe_path(root, name):
    require(type(name) is str and bool(name) and len(name) <= 256 and "\\" not in name and ":" not in name,
            "unsafe relative path")
    parts = name.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{x}" for x in range(1, 10)), *(f"LPT{x}" for x in range(1, 10))}
    require(not PurePosixPath(name).is_absolute() and all(p not in ("", ".", "..") and p.rstrip(" .") == p
            and p.split(".")[0].upper() not in reserved and not any(c in p for c in '<>"|?*')
            and not any(ord(c) < 32 for c in p) for p in parts), "unsafe relative path")
    result = root.joinpath(*parts)
    require(result.resolve().is_relative_to(root.resolve()), "path escapes project")
    for path in (result, *result.parents):
        if path == root:
            break
        if path.exists() or path.is_symlink():
            no_redirect(path)
    return result


def read_bytes(path, maximum):
    no_redirect(path)
    require(path.is_file() and path.stat().st_size <= maximum, "file size/type limit", "unsupported")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "file size limit", "unsupported")
    return raw


@contextmanager
def exclusive(root):
    path = safe_path(root, LOCK)
    try:
        handle = path.open("xb")
    except FileExistsError as exc:
        raise ContractError("busy", "application running or incomplete prior process; explicit diagnosis required") from exc
    try:
        with handle:
            handle.write(str(os.getpid()).encode("ascii"))
            handle.flush()
        yield
    finally:
        path.unlink()


def strict_json(raw):
    # Same strict decoder used by typed contracts: duplicate keys/floats rejected.
    return loads(dict, raw)


def report_for(checker, definition, project, project_id):
    report = to_data(checker(definition, project, project_id=project_id))
    require(report["definition_hash"] == digest(definition) and report["project_hash"] == digest(project),
            "checker report binding mismatch", "error")
    allowed = {"satisfied", "violated", "unknown", "not_applicable", "error"}
    require(all(x["status"] in allowed for x in report["outcomes"]), "invalid checker status", "error")
    return report


def savable(report):
    return all(x["status"] in ("satisfied", "not_applicable") for x in report["outcomes"])


def scoped(project, previous, view):
    old = {o.id: o for o in previous.objects} if previous else {}
    new = {o.id: o for o in project.objects}
    require(not previous or project.id == previous.id, "project identity changed", "conflict")
    for identity in old.keys() | new.keys():
        before, after = old.get(identity), new.get(identity)
        if before == after:
            continue
        require(all(o is None or o.entity in view["entities"] for o in (before, after)), "entity outside view edit scope", "forbidden")
        old_slots = {s.field: s for s in before.slots} if before else {}
        new_slots = {s.field: s for s in after.slots} if after else {}
        require(all(old_slots.get(f) == new_slots.get(f) or f in view["fields"]
                    for f in old_slots.keys() | new_slots.keys()), "field outside view edit scope", "forbidden")
    old_links = set(previous.links) if previous else set()
    require(all(link.relation in view["relations"] for link in old_links ^ set(project.links)),
            "relation outside view edit scope", "forbidden")


def check_target_paths(spec, definition, baseline, used_versions, checker):
    """One complete view/task path only. Same scope/version rules as actual save.

    This is preflight, not HTTP execution or a replacement for business acceptance.
    Baseline is the recorded delivery-time data; future saves do not rewrite it.
    """
    views = [view for view in spec["views"]
             if all(set(view[k]) == set(spec["edit_scope"][k]) for k in ("entities", "fields", "relations"))
             and {t["action"] for t in spec["tasks"] if t["view_id"] == view["id"]} == {"edit", "check", "save", "load"}]
    require(bool(views), "target requires one complete edit/check/save/load view; multi-view composition unsupported", "unsupported")
    previous = decode(ProjectModel, baseline) if baseline is not None else None
    supported = []
    for case in spec["acceptance_cases"]:
        project = decode(ProjectModel, case["project"])
        report = report_for(checker, definition, project, spec["project_id"])
        if not (case["public"] and project.population_complete and savable(report)):
            continue
        if project.version in used_versions:
            continue
        for view in views:
            try:
                scoped(project, previous, view)
            except ContractError:
                continue
            supported.append({"case_ref":case["ref"], "view_id":view["id"], "steps":case["steps"]})
            break
    require(bool(supported), "no public successful case can save with this target's task/view/version rules", "unsupported")
    return supported


def entry(definition, project, checker, project_id, parent):
    report = report_for(checker, definition, project, project_id)
    require(savable(report), "data has violated/unknown/error obligations", "data_conflict")
    body = {"definition": to_data(definition), "project": to_data(project), "report": report, "parent": parent}
    return {**body, "hash": digest(body)}


def read_store(root, relative_path, checker, project_id):
    path = safe_path(root, relative_path)
    require(not safe_path(root, relative_path + ".pending").exists(), "incomplete data write; no automatic recovery", "incomplete_write")
    data = strict_json(read_bytes(path, MAX_STORE).decode("utf-8"))
    require(set(data) == {"schema_version", "project_id", "entries"} and data["schema_version"] == "local-project-data/0.1"
            and data["project_id"] == project_id and type(data["entries"]) is list, "invalid data store", "corrupt")
    previous = None
    for item in data["entries"]:
        require(type(item) is dict and set(item) == {"definition", "project", "report", "parent", "hash"},
                "invalid history entry", "corrupt")
        definition = decode(DomainDefinition, item["definition"])
        project = decode(ProjectModel, item["project"])
        require(item == entry(definition, project, checker, project_id, previous), "data chain/report mismatch", "corrupt")
        previous = item["hash"]
    return data


def verify_files(root):
    manifest = strict_json(read_bytes(safe_path(root, MANIFEST), MAX_STORE).decode("utf-8"))
    require(manifest["schema_version"] == "local-web-delivery/0.1", "unsupported manifest", "unsupported")
    seen = set()
    for file in manifest["files"]:
        require(file["path"].casefold() not in seen, "duplicate manifest file", "corrupt")
        seen.add(file["path"].casefold())
        path = safe_path(root, file["path"])
        require(file["owner"] in ("generated", "human", "data"), "unknown file owner", "corrupt")
        if file["owner"] == "generated":
            require(hash_bytes(read_bytes(path, MAX_STORE)) == file["sha256"], "generated file changed: " + file["path"], "conflict")
    return manifest


class Engine:
    def __init__(self, root, checker):
        self.root, self.checker = directory(root), checker
        self.manifest = verify_files(self.root)
        self.settings = strict_json(read_bytes(safe_path(self.root, "settings.json"), MAX_STORE).decode("utf-8"))
        self.spec = self.settings["spec"]
        self.definition = decode(DomainDefinition, self.settings["definition"])
        self.project_id = self.spec["project_id"]
        require(digest(self.settings["spec"]) == self.manifest["spec_ref"]["content_hash"], "spec hash mismatch", "corrupt")
        self.storage = self.spec["storage"]["relative_path"]
        self.mutex = threading.Lock()
        self.store()  # Reverify actual persisted history before serving.

    def store(self):
        data = read_store(self.root, self.storage, self.checker, self.project_id)
        if data["entries"]:
            latest = data["entries"][-1]
            require(latest["definition"] == to_data(self.definition), "stale data definition", "conflict")
        return data

    def state(self, data=None):
        data = self.store() if data is None else data
        return {"status": "loaded", "revision": len(data["entries"]),
                "project_text": dumps(data["entries"][-1]["project"]) if data["entries"] else None,
                "settings": {k: self.spec[k] for k in ("views", "tasks", "edit_scope")}}

    def execute(self, action, body):
        require(type(body) is dict and set(body) == {"task_id", "expected_revision", "project_text"}, "invalid request fields")
        require(type(body["expected_revision"]) is int and type(body["project_text"]) is str, "invalid request types")
        task = next((t for t in self.spec["tasks"] if t["id"] == body["task_id"] and t["action"] == action), None)
        require(task is not None and action in self.spec["access"]["allowed_actions"], "task not authorized", "forbidden")
        with self.mutex:
            data = self.store()
            if action == "load":
                return 200, self.state(data)
            require(body["expected_revision"] == len(data["entries"]), "stale data version", "conflict")
            project = loads(ProjectModel, body["project_text"])
            previous = decode(ProjectModel, data["entries"][-1]["project"]) if data["entries"] else None
            view = next(v for v in self.spec["views"] if v["id"] == task["view_id"])
            scoped(project, previous, view)
            report = report_for(self.checker, self.definition, project, self.project_id)
            if action == "check":
                return 200, {"status": "checked", "save_allowed": savable(report), "report": report}
            require(action == "save", "unknown action", "forbidden")
            if not savable(report):
                return 422, {"status": "rejected", "report": report}
            require(not any(x["project"]["version"] == project.version for x in data["entries"]), "project version already used", "conflict")
            parent = data["entries"][-1]["hash"] if data["entries"] else None
            data["entries"].append(entry(self.definition, project, self.checker, self.project_id, parent))
            raw = dumps(data).encode("utf-8")
            require(len(raw) <= MAX_STORE, "retained history storage limit; nothing pruned", "unsupported")
            pending = safe_path(self.root, self.storage + ".pending")
            with pending.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, safe_path(self.root, self.storage))
            require(self.store() == data, "data read-after-write mismatch", "corrupt")
            return 200, {**self.state(data), "status": "saved", "report": report}

    def build(self):
        paths = check_target_paths(self.spec, self.definition, self.settings["acceptance_baseline"],
                                   self.settings["acceptance_used_versions"], self.checker)
        for file in self.manifest["files"]:
            if file["owner"] == "generated" and file["path"].endswith(".py"):
                compile(read_bytes(safe_path(self.root, file["path"]), MAX_STORE), file["path"], "exec")
        results = []
        for case in self.spec["acceptance_cases"]:
            project = decode(ProjectModel, case["project"])
            report = report_for(self.checker, self.definition, project, self.project_id)
            observed = [{k: x[k] for k in ("obligation", "target", "status")} for x in report["outcomes"]]
            require(observed == case["expected_outcomes"], "public acceptance mismatch", "conflict")
            results.append({"ref": case["ref"], "report": report})
        return {"status": "built", "acceptance": results, "task_path_preflight": paths,
                "runtime": "python-standard-library", "recovery": "unsupported"}


def serve(engine, port, stop_on_stdin_eof=False):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            pass  # No credentials/ProjectModel contents in request logs.

        def respond(self, status, raw, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def handle_request(self, post):
            try:
                host = "127.0.0.1:" + str(self.server.server_port)
                require(self.headers.get_all("Host") == [host], "invalid Host", "forbidden")
                origins = self.headers.get_all("Origin")
                require(origins is None or origins == ["http://" + host], "invalid Origin", "forbidden")
                require(self.headers.get("Sec-Fetch-Site") not in ("cross-site", "same-site"), "cross-site request", "forbidden")
                if self.path.startswith("/api/"):
                    credentials = self.headers.get_all("X-Session-Token")
                    require(credentials is not None and len(credentials) == 1 and secrets.compare_digest(credentials[0], token),
                            "session credential required", "forbidden")
                    if not post:
                        require(self.path == "/api/state", "unknown route", "not_found")
                        with engine.mutex:
                            result = engine.state()
                        self.respond(200, dumps(result).encode("utf-8"))
                        return
                    require(origins == ["http://" + host], "Origin required", "forbidden")
                    require(self.path in ("/api/load", "/api/check", "/api/save"), "unknown route", "not_found")
                    require(self.headers.get_all("Content-Type") == ["application/json"] and self.headers.get("Transfer-Encoding") is None,
                            "unsupported request encoding")
                    lengths = self.headers.get_all("Content-Length")
                    require(lengths is not None and len(lengths) == 1 and lengths[0].isdigit(), "content length required")
                    size = int(lengths[0])
                    require(0 < size <= MAX_REQUEST, "request size limit", "too_large")
                    raw = self.rfile.read(size)
                    require(len(raw) == size, "incomplete request")
                    status, result = engine.execute(self.path.rsplit("/", 1)[1], strict_json(raw.decode("utf-8")))
                    self.respond(status, dumps(result).encode("utf-8"))
                    return
                files = {"/": ("index.html", "text/html; charset=utf-8"), "/client.js": ("client.js", "text/javascript; charset=utf-8"),
                         "/style.css": ("style.css", "text/css; charset=utf-8")}
                require(not post and self.path in files, "unknown route", "not_found")
                name, mime = files[self.path]
                self.respond(200, read_bytes(safe_path(engine.root, name), MAX_REQUEST), mime)
            except (ValueError, UnicodeError, RecursionError, OSError) as exc:
                code = getattr(exc, "code", "error")
                status = {"conflict":409, "busy":409, "forbidden":403, "not_found":404, "too_large":413,
                          "unsupported":422, "invalid":400}.get(code, 500)
                self.respond(status, dumps({"status":code, "message":str(exc)}).encode("utf-8"))

        def do_GET(self):
            self.handle_request(False)

        def do_POST(self):
            self.handle_request(True)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = False
    try:
        if stop_on_stdin_eof:
            # Explicit local process supervision for detached acceptance hosts.
            # No network administration action is added to the application profile.
            def watch_parent():
                sys.stdin.buffer.read()
                server.shutdown()
            threading.Thread(target=watch_parent, daemon=True).start()
        print(dumps({"status":"serving", "url":f"http://127.0.0.1:{server.server_port}/#{token}"}), flush=True)
        server.serve_forever()
    finally:
        server.server_close()


def main(root, checker, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "serve"))
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--stop-on-stdin-eof", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = directory(root)
        with exclusive(root):
            engine = Engine(root, checker)
            if args.command == "build":
                print(dumps(engine.build()))
            else:
                require(not (root / ".incomplete-delivery").exists(), "delivery build incomplete", "incomplete_write")
                engine.build()
                serve(engine, args.port, args.stop_on_stdin_eof)
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, UnicodeError, RecursionError) as exc:
        print(dumps({"status":getattr(exc, "code", "error"), "message":str(exc)}))
        return 2
