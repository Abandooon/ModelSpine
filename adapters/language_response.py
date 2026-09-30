"""One stateless Responses transport. No retries, redirects, SDK or model fallback."""
from dataclasses import dataclass, field
import base64
import http.client
import json
from pathlib import Path
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "language-response/0.1.1"
MAX_ENVELOPE_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 120
NAMES = ("MODELSPINE_PROVIDER_URL", "MODELSPINE_BASE_URL", "MODELSPINE_API_KEY",
         "MODELSPINE_MODEL", "MODELSPINE_MAX_REQUESTS", "MODELSPINE_MAX_OUTPUT_TOKENS")


class LanguageError(ValueError):
    """Codes are fixed local strings, never remote exception text or configuration."""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise LanguageError("duplicate_json_key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(LanguageError("nonfinite_json")))
    except (ValueError, UnicodeError, RecursionError):
        raise LanguageError("invalid_json") from None


@dataclass(frozen=True)
class Config:
    provider_url: str
    base_url: str
    key: str = field(repr=False)
    model: str
    max_requests: int
    max_output_tokens: int

    def public(self):
        return {"provider_url": self.provider_url, "base_url": self.base_url, "model": self.model,
                "max_requests": self.max_requests, "max_output_tokens": self.max_output_tokens,
                "protocol": "responses", "timeout_seconds": TIMEOUT_SECONDS}

    def validate(self):
        if self.model != "gpt-6-luna" or self.base_url != "https://api.openai-proxy.org/v1":
            raise LanguageError("explicit_model_or_endpoint_mismatch")
        url = urllib.parse.urlsplit(self.provider_url)
        if (url.scheme != "https" or url.netloc != "api.openai-proxy.org" or
                url.path not in ("", "/", "/v1") or url.query or url.fragment):
            raise LanguageError("provider_url_mismatch")
        if not self.key or any(c.isspace() for c in self.key) or not self.key.isascii():
            raise LanguageError("invalid_credential")
        if type(self.max_requests) is not int or not 1 <= self.max_requests <= 3:
            raise LanguageError("invalid_request_budget")
        if type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= 4096:
            raise LanguageError("invalid_output_budget")
        return self


def load_config(env_file):
    """Read only six exact names in-process; no interpolation, exports or logging."""
    path = Path(env_file)
    try:
        if not path.is_absolute() or path.is_symlink():
            raise LanguageError("explicit_config_path_required")
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise LanguageError("config_size_limit")
        values = {}
        for line in raw.decode("utf-8-sig").splitlines():
            name, sep, value = line.partition("=")
            name = name.strip()
            if not sep or name not in NAMES:
                continue
            if name in values:
                raise LanguageError("duplicate_config_name")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[name] = value
        if set(values) != set(NAMES) or any(not v for v in values.values()):
            raise LanguageError("missing_configuration")
        return Config(values[NAMES[0]], values[NAMES[1]], values[NAMES[2]], values[NAMES[3]],
                      int(values[NAMES[4]]), int(values[NAMES[5]])).validate()
    except (OSError, UnicodeError, ValueError) as exc:
        code = str(exc) if isinstance(exc, LanguageError) else "invalid_configuration"
        raise LanguageError(code) from None


def redact(raw, key):
    """Preserve original bytes unless credential text is found. Never store originals on a hit."""
    variants = {key.encode(), json.dumps(key)[1:-1].encode(),
                urllib.parse.quote(key, safe="").encode(), base64.b64encode(key.encode()),
                "".join("\\u%04x" % ord(c) for c in key).encode()}
    clean = raw
    for value in sorted(variants, key=len, reverse=True):
        clean = clean.replace(value, b"[REDACTED_CREDENTIAL]")
    # JSON string escapes are recognizable without a complete JSON document.
    # Config limits keys to ASCII; hex digit case may vary, literal case may not.
    tokens = []
    for char in key:
        forms = {re.escape(char.encode()), re.escape(json.dumps(char)[1:-1].encode()),
                 rb"\\u(?i:%04x)" % ord(char)}
        if char == "/":
            forms.add(re.escape(b"\\/"))
        tokens.append(b"(?:" + b"|".join(sorted(forms)) + b")")
    credential = re.compile(b"".join(tokens))
    # Match complete strings or a valid received prefix at EOF, keeping any
    # unfinished escape separate. No closing quote is added to saved bytes.
    strings = re.compile(rb'"((?:[^"\\]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*)("|\\(?:u[0-9a-fA-F]{0,3})?\Z|\Z)')
    def json_echoes(data, depth=0):
        data = credential.sub(b"[REDACTED_CREDENTIAL]", data)
        if depth == 4:
            return data
        def visit(match):
            # Decode only complete characters for credential detection, even if
            # the string/envelope is unfinished. Reattach its actual terminator.
            try:
                text = json.loads(b'"' + match[1] + b'"').encode("utf-8")
                safe = json_echoes(text, depth + 1)
                if safe != text:
                    quoted = json.dumps(safe.decode("utf-8"), ensure_ascii=False).encode("utf-8")
                    return quoted[:-1] + match[2]
            except (ValueError, UnicodeError):
                pass
            return match[0]
        return strings.sub(visit, data)
    clean = json_echoes(clean)
    return clean, clean != raw


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect rejected", headers, fp)


@dataclass(frozen=True)
class Exchange:
    http_status: int | None
    raw: bytes
    transport_status: str


def post_response(config, payload):
    """Exactly one POST; system proxy and verified TLS remain enabled."""
    config.validate()
    request = urllib.request.Request(config.base_url + "/responses", data=payload, method="POST",
                                     headers={"Authorization": "Bearer " + config.key,
                                              "Content-Type": "application/json", "Accept": "application/json"})
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    status = None
    raw = b""
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            while len(raw) <= MAX_ENVELOPE_BYTES:
                # read1 returns available body bytes instead of filling amt: a later
                # socket timeout cannot swallow a prefix already delivered here.
                chunk = response.read1(min(65536, MAX_ENVELOPE_BYTES + 1 - len(raw)))
                if not chunk:
                    if response.length is not None and response.length > 0:
                        return Exchange(status, raw, "truncated_http_body")
                    break
                raw += chunk
                if time.monotonic() >= deadline:
                    return Exchange(status, raw, "timeout")
            if len(raw) > MAX_ENVELOPE_BYTES:
                return Exchange(status, raw, "response_size_limit")
            return Exchange(status, raw, "received")
    except (TimeoutError, socket.timeout):
        return Exchange(status, raw, "timeout")
    except http.client.IncompleteRead as error:
        return Exchange(status, raw + error.partial, "truncated_http_body")
    except urllib.error.URLError as error:
        return Exchange(status, raw, "timeout" if isinstance(error.reason, TimeoutError) else "network_error")
    except (OSError, http.client.HTTPException):
        return Exchange(status, raw, "network_error")


def extract_response(raw, requested_model):
    """Closed extraction: one assistant message with one output_text; optional reasoning items."""
    data = strict_json(raw)
    if not isinstance(data, dict) or data.get("object") != "response":
        raise LanguageError("invalid_response_envelope")
    usage = data.get("usage")
    usage_known = (isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0
                   for k in ("input_tokens", "output_tokens", "total_tokens")))
    if usage_known:
        usage_known = usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
    info = {"response_id": data.get("id"), "returned_model": data.get("model"),
            "response_status": data.get("status"), "incomplete_details": data.get("incomplete_details"),
            "usage": usage if usage_known else None, "usage_status": "reported" if usage_known else "unknown",
            "cost": None, "cost_status": "not_measured", "stop_reasons": []}
    for condition, reason in ((data.get("model") != requested_model, "response_model_mismatch"),
                              (data.get("status") != "completed", "response_not_completed"),
                              (data.get("error") is not None, "provider_error"),
                              (not usage_known, "usage_unknown")):
        if condition:
            info["stop_reasons"].append(reason)
    output = data.get("output")
    candidate = None
    if isinstance(output, list) and all(isinstance(x, dict) and x.get("type") in ("reasoning", "message") for x in output):
        messages = [x for x in output if x.get("type") == "message"]
        if len(messages) == 1:
            message = messages[0]
            content = message.get("content")
            if (message.get("role") == "assistant" and isinstance(content, list) and len(content) == 1
                    and isinstance(content[0], dict) and content[0].get("type") == "output_text"
                    and type(content[0].get("text")) is str):
                try:
                    candidate = content[0]["text"].encode("utf-8")
                except UnicodeError:
                    pass
            if message.get("status") != "completed":
                info["stop_reasons"].append("message_not_completed")
    if candidate is None:
        info["stop_reasons"].append("unsupported_output_shape")
    info["extraction"] = "exact_output_text_utf8" if candidate is not None else "not_extracted"
    return candidate, info
