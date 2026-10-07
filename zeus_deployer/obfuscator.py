import re
import uuid
import secrets
from typing import Dict, Any

DISGUISED_PREFIXES = [
    "cloud-sync", "edge-cache", "telemetry-stream", "analytics-node",
    "data-pipeline", "metric-agent", "ingress-router", "packet-relay",
    "cdn-optimizer", "beacon-hub", "nexus-flow", "gateway-mesh"
]


def generate_random_repo_name(prefix: str = "") -> str:
    if not prefix:
        prefix = secrets.choice(DISGUISED_PREFIXES)
    return f"{prefix}-{secrets.token_hex(3)}"


def generate_admin_path() -> str:
    return f"/admin_{secrets.token_hex(4)}"


def generate_uuid() -> str:
    return str(uuid.uuid4())


def generate_d1_name() -> str:
    return f"db_{secrets.token_hex(4)}"


def _is_ident(ch: str) -> bool:
    return bool(ch) and (ch.isalnum() or ch in "_$")


def _regex_can_start(prev_sig: str | None) -> bool:
    # JavaScript regex literals can occur after these token classes/keywords.
    if prev_sig is None:
        return True
    return prev_sig in "([{=,:;!&|?+-*%^~<>" or prev_sig in {"return", "throw", "case", "delete", "void", "typeof", "instanceof", "in", "of", "yield", "await", "else", "do"}


def safe_minify_javascript(source: str) -> str:
    """Conservative JS minifier: removes comments and redundant whitespace only.

    It deliberately does not rename identifiers or rewrite string/template literals,
    imports, regex literals, or expressions. This keeps large Cloudflare Workers
    (including integrity-sensitive code) behaviorally stable while still producing a
    compact/obfuscated build artifact.
    """
    out: list[str] = []
    i = 0
    n = len(source)
    pending_space = False
    prev_sig: str | None = None

    def emit(value: str, significant: bool = True):
        nonlocal pending_space, prev_sig
        if pending_space and out and value and (_is_ident(out[-1][-1:]) and _is_ident(value[:1])):
            out.append(" ")
        pending_space = False
        out.append(value)
        if significant and value:
            prev_sig = value if value in {"return", "throw", "case", "delete", "void", "typeof", "instanceof", "in", "of", "yield", "await", "else", "do"} else value[-1]

    while i < n:
        c = source[i]
        # Line/block comments
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            i += 2
            while i < n and source[i] not in "\r\n":
                i += 1
            pending_space = True
            continue
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            end = source.find("*/", i + 2)
            i = n if end < 0 else end + 2
            pending_space = True
            continue

        # Strings / template literals. Template expressions are kept byte-for-byte.
        if c in "'\"`":
            quote = c
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == quote:
                    j += 1
                    break
                j += 1
            emit(source[i:j])
            i = j
            continue

        # Regex literal. Conservative lexical handling to avoid touching /.../g.
        if c == "/" and _regex_can_start(prev_sig):
            j = i + 1
            in_class = False
            ok = False
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == "[":
                    in_class = True
                elif source[j] == "]":
                    in_class = False
                elif source[j] == "/" and not in_class:
                    j += 1
                    while j < n and source[j].isalpha():
                        j += 1
                    ok = True
                    break
                elif source[j] in "\r\n":
                    break
                j += 1
            if ok:
                emit(source[i:j])
                i = j
                continue

        if c.isspace():
            pending_space = True
            i += 1
            continue

        # Punctuation never needs surrounding whitespace.
        if pending_space and out:
            left = out[-1][-1:]
            if _is_ident(left) and _is_ident(c):
                out.append(" ")
        pending_space = False
        out.append(c)
        prev_sig = c
        i += 1

    return "".join(out).strip()


def obfuscate_worker_js(source_code: str, config: Dict[str, Any]) -> str:
    """Build-time safe obfuscation/minification for the real ZEUS source.

    We intentionally avoid string-table replacement, identifier mangling, anti-debug
    loops, or code injection. Those techniques can break Cloudflare Workers and can
    invalidate upstream integrity checks. The deployer therefore performs a
    semantics-preserving lexical minification before upload and records build metadata.
    """
    code = source_code
    # Support existing custom templates without changing the official ZEUS source.
    replacements = {
        "{{NODE_NAME}}": config.get("repo_name", "edge-node"),
        "{{ADMIN_PATH}}": config.get("admin_path", "/admin_secret"),
        "{{ROOT_UUID}}": config.get("uuid", generate_uuid()),
        "{{D1_DATABASE}}": config.get("d1_name", "d1_zeus"),
        "{{SALT_KEY}}": config.get("salt", secrets.token_hex(16)),
    }
    for needle, value in replacements.items():
        code = code.replace(needle, str(value))

    minified = safe_minify_javascript(code)
    marker = f"/* ZEUS BUILD: {secrets.token_hex(8)} */\n"
    return marker + minified


def generate_wrangler_toml(repo_name: str, d1_name: str, admin_path: str, uuid_str: str, d1_id: str = "") -> str:
    d1_id = d1_id or "REPLACE_WITH_REAL_D1_ID"
    return f'''name = "{repo_name}"
main = "_worker.js"
compatibility_date = "2026-10-07"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "{d1_name}"
database_id = "{d1_id}"

[vars]
ADMIN_PATH = "{admin_path}"
UUID = "{uuid_str}"
'''


def generate_cover_readme(repo_name: str) -> str:
    return f'''# {repo_name}

Automated ZEUS Cloudflare Worker deployment artifact.

## Deployment
Generated automatically from the official ZEUS source repository and configured for Cloudflare Workers + D1.
'''
