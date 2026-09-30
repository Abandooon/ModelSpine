"""Loopback-only finite review host; one explicit local project per process."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_review import create_review, read_review, submit_action

# This package is not yet in bootstrap's registered package list. Local app assembly
# exposes its single source directory; integration owns the later manifest update.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/interaction/src"))
from modelspine_interaction.review_ui import project_review, review_asset, review_page
from modelspine_protocols import ContractError, loads
from modelspine_protocols.review import ReviewAction, WHOLE_CANDIDATE
from modelspine_requirements.domain_modeling import ModelingRequest

MAX_ACTION_BYTES = 512 * 1024


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, project_dir, *, port=0, actor="local-reviewer"):
        root = Path(project_dir)
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("explicit existing absolute project directory required")
        if not actor.strip():
            raise ValueError("actor must be a nonempty attribution label")
        read_review(root)  # A owns directory, integrity and saved-session validation.
        self.project_dir = root
        self.actor = actor
        self.action_token = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), ReviewHandler)
        self.authority = f"127.0.0.1:{self.server_port}"
        self.origin = "http://" + self.authority


class ReviewHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def reply(self, status, data, content_type="application/json; charset=utf-8"):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8") if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(raw)

    def fail(self, status, code, reason):
        self.reply(status, {"status":"error", "code":code, "reason":reason})

    def guard(self, *, action=False, private=False):
        for name in ("Host", "Origin", "X-Review-Token", "Content-Length", "Content-Type", "Sec-Fetch-Site"):
            if len(self.headers.get_all(name, [])) > 1:
                self.fail(400, "invalid_http", "duplicate boundary header")
                return False
        origin = self.headers.get("Origin")
        if (self.headers.get("Host") != self.server.authority or
                (origin is not None and origin != self.server.origin) or
                self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none")):
            self.fail(403, "forbidden", "request source rejected")
            return False
        if self.headers.get("Transfer-Encoding") is not None:
            self.fail(400, "invalid_http", "transfer encoding unsupported")
            return False
        if (action and origin != self.server.origin) or ((action or private) and
                not secrets.compare_digest(self.headers.get("X-Review-Token", "").encode("utf-8"), self.server.action_token.encode("ascii"))):
            self.fail(403, "forbidden", "origin/action capability required")
            return False
        return True

    def error_from(self, exc):
        code = exc.code if isinstance(exc, ContractError) else "input_or_io_error"
        status = {"conflict":409, "busy":423, "corrupt":500, "incomplete_write":500}.get(code, 400)
        if isinstance(exc, OSError):
            status = 500
        self.fail(status, code, str(exc))

    def do_GET(self):
        if not self.guard(private=self.path == "/api/review"):
            return
        if self.headers.get("Content-Length", "0") != "0":
            self.fail(400, "invalid_http", "GET body unsupported")
            return
        try:
            if self.path == "/":
                self.reply(200, review_page(self.server.action_token).encode("utf-8"), "text/html; charset=utf-8")
            elif self.path in ("/review.js", "/review.css"):
                kind = "text/javascript" if self.path.endswith(".js") else "text/css"
                self.reply(200, review_asset(self.path[1:]), kind + "; charset=utf-8")
            elif self.path == "/api/review":
                view = read_review(self.server.project_dir)
                self.reply(200, {"view": view, "presentation":project_review(view), "actor":self.server.actor,
                                 "whole_candidate":WHOLE_CANDIDATE})
            else:
                self.fail(404, "not_found", "unknown route; project directory is fixed at startup")
        except (ValueError, OSError, RecursionError) as exc:
            self.error_from(exc)

    def do_POST(self):
        if not self.guard(action=True):
            return
        if self.path != "/api/action":
            self.fail(404, "not_found", "unknown action route")
            return
        if self.headers.get("Content-Type") != "application/json":
            self.fail(415, "invalid_http", "application/json required")
            return
        length = self.headers.get("Content-Length", "")
        if not length.isascii() or not length.isdecimal() or len(length) > 7:
            self.fail(411, "invalid_http", "single decimal Content-Length required")
            return
        size = int(length)
        if not 0 < size <= MAX_ACTION_BYTES:
            self.fail(413, "unsupported", "action body must be 1..512 KiB")
            return
        try:
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("incomplete request body")
            action = loads(ReviewAction, raw.decode("utf-8"))
            if action.actor != self.server.actor:
                raise ValueError("actor differs from host attribution label")
            receipt = submit_action(self.server.project_dir, action)
            self.reply(200, receipt)
        except (ValueError, OSError, RecursionError) as exc:
            self.error_from(exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--actor", default="local-reviewer")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--session-id")
    args = parser.parse_args(argv)
    try:
        if any(v is not None for v in (args.request, args.candidate, args.session_id)):
            if not all(v is not None for v in (args.request, args.candidate, args.session_id)):
                raise ValueError("creation requires --request, --candidate and --session-id together")
            with args.request.open("rb") as stream:
                request_raw = stream.read(512 * 1024 + 1)
            if len(request_raw) > 512 * 1024:
                raise ValueError("request exceeds 512 KiB")
            with args.candidate.open("rb") as stream:
                candidate = stream.read(256 * 1024 + 1)
            create_review(args.project_dir, loads(ModelingRequest, request_raw.decode("utf-8")), candidate,
                          session_id=args.session_id)
        with ReviewServer(args.project_dir, port=args.port, actor=args.actor) as server:
            print(json.dumps({"url":server.origin, "project_dir":str(args.project_dir),
                              "scope":"finite_review_only"}), flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, RecursionError) as exc:
        print(json.dumps({"status":"error", "reason":str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
