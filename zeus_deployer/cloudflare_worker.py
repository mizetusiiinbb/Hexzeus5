import json
import secrets
import re
from urllib.parse import urlparse
from workers import WorkerEntrypoint, Response, fetch

from zeus_deployer.obfuscator import generate_random_repo_name, generate_admin_path, generate_uuid, generate_d1_name, obfuscate_worker_js

SOURCE_URL = "https://raw.githubusercontent.com/panel-zeus/Z-E-U-S/main/Source.js"
GITHUB_REPO = "https://github.com/panel-zeus/Z-E-U-S"
COMPATIBILITY_DATE = "2026-10-07"


def clean_worker_name(value):
    value = (value or "").strip()
    if not value:
        return generate_random_repo_name()
    value = re.sub(r"[^A-Za-z0-9-]", "-", value).strip("-")
    return value[:63] or generate_random_repo_name()


def clean_admin_path(value):
    value = (value or "").strip()
    if not value:
        return generate_admin_path()
    if not value.startswith("/"):
        value = "/" + value
    value = re.sub(r"[^A-Za-z0-9_\-/]", "", value)
    return value.rstrip("/") or generate_admin_path()


async def cf_json(url, token, method="GET", body=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    opts = {"method": method, "headers": headers}
    if body is not None:
        opts["body"] = json.dumps(body)
    res = await fetch(url, opts)
    try:
        data = await res.json()
    except Exception:
        data = {"success": False, "errors": [{"message": await res.text()}]}
    return res, data


def multipart_upload(script_name, source, metadata):
    boundary = "----zeusdeploy" + secrets.token_hex(12)
    meta = json.dumps(metadata, separators=(",", ":"))
    chunks = []
    chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n{meta}\r\n".encode())
    chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"_worker.js\"; filename=\"_worker.js\"\r\nContent-Type: application/javascript+module\r\n\r\n".encode())
    chunks.append(source.encode("utf-8"))
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


async def deploy(token, custom_name=None, custom_admin_path=None):
    token = (token or "").strip()
    if not token:
        return {"status": "error", "detail": "توکن Cloudflare الزامی است."}, 400

    verify_res, verify = await cf_json("https://api.cloudflare.com/client/v4/user/tokens/verify", token)
    if verify_res.status != 200 or not verify.get("success"):
        return {"status": "error", "detail": "توکن Cloudflare نامعتبر است یا دسترسی لازم را ندارد."}, 401

    acc_res, acc_data = await cf_json("https://api.cloudflare.com/client/v4/accounts", token)
    accounts = acc_data.get("result") or []
    if acc_res.status != 200 or not accounts:
        return {"status": "error", "detail": "هیچ Account قابل استفاده‌ای برای این توکن پیدا نشد."}, 400

    account = accounts[0]
    account_id = account["id"]
    account_name = account.get("name", account_id)
    script_name = clean_worker_name(custom_name)
    admin_path = clean_admin_path(custom_admin_path)
    d1_name = generate_d1_name()
    uuid_value = generate_uuid()
    d1_id = None
    created_d1 = False

    try:
        # Pull the real ZEUS source directly from GitHub. No GitHub token is needed.
        source_res = await fetch(SOURCE_URL, {"method": "GET", "headers": {"Accept": "text/plain"}})
        if source_res.status != 200:
            return {"status": "error", "detail": "دریافت سورس رسمی ZEUS از GitHub ناموفق بود."}, 502
        source = await source_res.text()
        original_source_bytes = len(source.encode("utf-8"))
        if "export default" not in source or "env.DB" not in source:
            return {"status": "error", "detail": "سورس دریافت‌شده ZEUS معتبر نیست یا ساختار مورد انتظار را ندارد."}, 502

        # Build-time safe obfuscation/minification. It intentionally avoids identifier
        # or string rewriting so ZEUS runtime/integrity-sensitive behavior is preserved.
        build_config = {
            "repo_name": script_name,
            "admin_path": admin_path,
            "uuid": uuid_value,
            "d1_name": d1_name,
            "salt": secrets.token_hex(16),
        }
        source = obfuscate_worker_js(source, build_config)
        if "{{" in source or "}}" in source or len(source) < 1000:
            return {"status": "error", "detail": "Build artifact validation failed; deployment stopped."}, 500

        d1_res, d1_data = await cf_json(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database",
            token,
            "POST",
            {"name": d1_name},
        )
        if d1_res.status not in (200, 201) or not d1_data.get("success"):
            return {"status": "error", "detail": "ساخت D1 شکست خورد؛ Worker بدون Database منتشر نشد.", "cloudflare": d1_data}, 400
        d1_id = (d1_data.get("result") or {}).get("uuid")
        if not d1_id:
            return {"status": "error", "detail": "Cloudflare برای D1 شناسه معتبر برنگرداند."}, 502
        created_d1 = True

        metadata = {
            "main_module": "_worker.js",
            "bindings": [{"type": "d1", "name": "DB", "id": d1_id}],
            "compatibility_date": COMPATIBILITY_DATE,
            "compatibility_flags": ["nodejs_compat"],
        }
        body, boundary = multipart_upload(script_name, source, metadata)
        upload = await fetch(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}",
            {
                "method": "PUT",
                "headers": {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                "body": body,
            },
        )
        if upload.status not in (200, 201):
            detail = await upload.text()
            raise RuntimeError(f"Worker upload failed ({upload.status}): {detail[:1000]}")

        sub_res, sub_data = await cf_json(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}/subdomain",
            token,
            "POST",
            {"enabled": True, "previews_enabled": False},
        )
        if sub_res.status not in (200, 201) or not sub_data.get("success"):
            raise RuntimeError("فعال‌سازی workers.dev برای Worker ناموفق بود.")

        domain_res, domain_data = await cf_json(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/subdomain", token
        )
        subdomain = (domain_data.get("result") or {}).get("subdomain")
        if not subdomain:
            raise RuntimeError("Cloudflare workers.dev subdomain را برنگرداند. ابتدا باید subdomain حساب فعال باشد.")

        live_domain = f"{script_name}.{subdomain}.workers.dev"
        return {
            "status": "success",
            "account_name": account_name,
            "script_name": script_name,
            "source_repo": GITHUB_REPO,
            "source_url": SOURCE_URL,
            "build": {"obfuscated": True, "method": "conservative-js-minify", "source_bytes": original_source_bytes, "deployed_bytes": len(source.encode("utf-8"))},
            "d1_database": d1_name,
            "d1_id": d1_id,
            "admin_path": admin_path,
            "uuid": uuid_value,
            "panel_url": f"https://{live_domain}/panel",
            "subscription_base_url": f"https://{live_domain}/sub/{{username}}",
            "live_url": f"https://{live_domain}",
        }, 200
    except Exception as exc:
        if created_d1 and d1_id:
            try:
                await cf_json(f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{d1_id}", token, "DELETE")
            except Exception:
                pass
        return {"status": "error", "detail": str(exc)}, 502


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = urlparse(request.url)
        if url.path == "/health":
            return Response.json({"ok": True, "service": "ZEUS Cloudflare Auto-Deployer"})

        if url.path == "/api/deploy/cloudflare" and request.method == "POST":
            try:
                body = await request.json()
            except Exception:
                body = {}
            result, status = await deploy(
                body.get("cf_token"),
                body.get("custom_name"),
                body.get("custom_admin_path"),
            )
            return Response.json(result, status=status)

        # Preserve the existing UI and serve it as a bundled asset.
        try:
            from pathlib import Path
            html = (Path(__file__).parent / "templates" / "index.html").read_text()
        except Exception:
            html = "<h1>ZEUS Deployer</h1>"
        return Response(html, headers={"Content-Type": "text/html; charset=utf-8"})
