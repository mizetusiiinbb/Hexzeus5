import re
import uuid
import secrets
import base64
import urllib.parse
from typing import Dict, Any, Tuple

DISGUISED_PREFIXES = [
    "cloud-sync", "edge-cache", "telemetry-stream", "analytics-node",
    "data-pipeline", "metric-agent", "ingress-router", "packet-relay",
    "cdn-optimizer", "beacon-hub", "nexus-flow", "gateway-mesh"
]

def generate_random_repo_name(prefix: str = "") -> str:
    """Generate a realistic, disguised repository name."""
    if not prefix:
        prefix = secrets.choice(DISGUISED_PREFIXES)
    suffix = secrets.token_hex(3)
    return f"{prefix}-{suffix}"

def generate_admin_path() -> str:
    """Generate a secret admin path."""
    return f"/admin_{secrets.token_hex(4)}"

def generate_uuid() -> str:
    """Generate a valid RFC4122 v4 UUID."""
    return str(uuid.uuid4())

def generate_d1_name() -> str:
    """Generate a custom D1 database name."""
    return f"db_{secrets.token_hex(4)}"

def obfuscate_worker_js(source_code: str, config: Dict[str, Any]) -> str:
    """
    Polymorphic JavaScript Obfuscation Engine:
    - Variable substitution for custom identities
    - String Array Extraction & Base64 Encoding
    - Array Rotation via IIFE
    - Dead code injection
    - Anti-beautify / self-defending guard
    """
    # 1. Substitute template tags
    code = source_code
    code = code.replace("{{NODE_NAME}}", config.get("repo_name", "edge-node"))
    code = code.replace("{{ADMIN_PATH}}", config.get("admin_path", "/admin_secret"))
    code = code.replace("{{ROOT_UUID}}", config.get("uuid", generate_uuid()))
    code = code.replace("{{D1_DATABASE}}", config.get("d1_name", "d1_zeus"))
    code = code.replace("{{SALT_KEY}}", config.get("salt", secrets.token_hex(16)))

    # 2. Extract string literals
    string_list = []
    string_map = {}

    def string_replacer(match):
        val = match.group(2)
        if not val or len(val) < 2:
            return match.group(0)
        if val not in string_map:
            string_map[val] = len(string_list)
            # Encode string in Base64
            encoded = base64.b64encode(urllib.parse.quote(val).encode("utf-8")).decode("utf-8")
            string_list.append(encoded)
        idx = string_map[val]
        return f"_0xdec(0x{idx:x})"

    # Match single and double quoted strings (excluding empty or single char)
    code = re.sub(r'(["\'])(.*?)\1', string_replacer, code)

    # 3. Build array, rotator, and decoder
    arr_name = f"_0x{secrets.token_hex(2)}"
    func_name = "_0xdec"
    rotator_offset = secrets.randbelow(150) + 50

    strings_joined = ",".join(f'"{s}"' for s in string_list)
    prefix_code = f"""/** (C) Polymorphic Edge Deployment Core - Protected */
var {arr_name} = [{strings_joined}];
(function(arr, offset) {{
  var rotator = function(count) {{
    while (--count) {{ arr.push(arr.shift()); }}
  }};
  rotator(++offset);
}})({arr_name}, 0x{rotator_offset:x});

var {func_name} = function(idx) {{
  idx = idx - 0;
  var str = {arr_name}[idx];
  try {{
    return decodeURIComponent(atob(str));
  }} catch(e) {{
    return atob(str);
  }}
}};
"""

    # 4. Anti-beautify guard
    anti_beautify = """(function() {
  var _0xguard = function() {
    var _0xtest = new RegExp('(\\\\w+)');
    return _0xtest.test(_0xguard.toString());
  };
  if (!_0xguard()) { while(true) {} }
})();
"""

    # 5. Dead code injection
    dead_code = f"""var _0x{secrets.token_hex(2)} = function(_0xa, _0xb) {{
  return (_0xa ^ _0xb) * 0x{secrets.token_hex(2)};
}};
var _0x{secrets.token_hex(2)} = [0x{secrets.token_hex(2)}, 0x{secrets.token_hex(2)}];
"""

    return f"{prefix_code}\n{anti_beautify}\n{dead_code}\n{code}"

def generate_wrangler_toml(repo_name: str, d1_name: str, admin_path: str, uuid_str: str) -> str:
    """Generate matching Cloudflare configuration manifest."""
    return f"""name = "{repo_name}"
main = "_worker.js"
compatibility_date = "2026-01-20"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "{d1_name}"
database_id = "d1-auto-generated-binding"

[vars]
ADMIN_PATH = "{admin_path}"
UUID = "{uuid_str}"
"""

def generate_cover_readme(repo_name: str) -> str:
    """Generate innocent, non-suspicious README for the repository."""
    return f"""# {repo_name}

An automated, low-latency telemetry caching and edge stream processor.

## Features
- Distributed edge response caching
- Real-time pipeline health checks
- Cloudflare Pages / Workers native runtime

## Deployment
This project is configured for automated edge deployment.
"""
