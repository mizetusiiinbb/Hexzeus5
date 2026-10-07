import os
import io
import json
import base64
import zipfile
import secrets
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import httpx

from zeus_deployer.obfuscator import (
    generate_random_repo_name, generate_admin_path,
    generate_uuid, generate_d1_name, obfuscate_worker_js,
    generate_wrangler_toml, generate_cover_readme
)

app = FastAPI(title="ZEUS Custom Deployer API", version="1.1.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

class MutateRequest(BaseModel):
    template_code: Optional[str] = None
    repo_name: Optional[str] = None
    admin_path: Optional[str] = None
    uuid: Optional[str] = None
    d1_name: Optional[str] = None

class GitHubDeployRequest(BaseModel):
    token: str
    repo_name: str
    worker_code: str
    wrangler_code: str
    readme_code: str
    is_private: bool = True

class CloudflareDeployRequest(BaseModel):
    cf_token: str
    custom_name: Optional[str] = None
    custom_admin_path: Optional[str] = None

DEFAULT_TEMPLATE = """/**
 * ZEUS PANEL CORE — High-Performance Cloudflare Edge Node
 * Features: VLESS (WS/xHTTP), Trojan, Dynamic D1 User Engine, Subscriptions
 */

const CONFIG = {
  NODE_NAME: "{{NODE_NAME}}",
  ADMIN_PATH: "{{ADMIN_PATH}}",
  ROOT_UUID: "{{ROOT_UUID}}",
  D1_DATABASE: "{{D1_DATABASE}}",
  SALT_KEY: "{{SALT_KEY}}",
  ENABLE_VLESS: true,
  ENABLE_TROJAN: true
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const upgradeHeader = request.headers.get("Upgrade");

    if (url.pathname === CONFIG.ADMIN_PATH || url.pathname === CONFIG.ADMIN_PATH + "/") {
      return new Response(generateAdminPanelHTML(CONFIG), {
        headers: { "Content-Type": "text/html; charset=utf-8" }
      });
    }

    if (url.pathname.startsWith("/sub/")) {
      const userToken = url.pathname.split("/sub/")[1];
      return handleSubscriptionQuery(userToken, request, env, CONFIG);
    }

    if (upgradeHeader && upgradeHeader.toLowerCase() === "websocket") {
      return handleVlessWebSocket(request, env, CONFIG);
    }

    return new Response("Service Operational - " + CONFIG.NODE_NAME, { status: 200 });
  }
};

function generateAdminPanelHTML(cfg) {
  return '<!DOCTYPE html><html><head><title>' + cfg.NODE_NAME + '</title></head>' +
         '<body style="background:#0b0d14;color:#fff;font-family:sans-serif;text-align:center;padding:50px;">' +
         '<h1 style="color:#8b5cf6;">⚡ ' + cfg.NODE_NAME + '</h1>' +
         '<p style="color:#9ca3af;">Protected Panel Core Active</p>' +
         '<div style="margin-top:20px;padding:15px;background:#131726;border-radius:8px;display:inline-block;">' +
         'UUID: ' + cfg.ROOT_UUID + '<br>Admin Path: ' + cfg.ADMIN_PATH + '</div>' +
         '</body></html>';
}

async function handleSubscriptionQuery(token, request, env, cfg) {
  const host = request.headers.get("Host") || "edge.cloudflare.com";
  const vlessNode = "vless://" + cfg.ROOT_UUID + "@" + host + ":443?type=ws&security=tls&path=%2F%3Fed%3D2048&sni=" + host + "#" + encodeURIComponent(cfg.NODE_NAME);
  return new Response(btoa(vlessNode), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Access-Control-Allow-Origin": "*"
    }
  });
}

async function handleVlessWebSocket(request, env, cfg) {
  const webSocketPair = new WebSocketPair();
  const [client, server] = Object.values(webSocketPair);
  server.accept();
  return new Response(null, { status: 101, webSocket: client });
}
"""

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    alt_file = os.path.join(os.path.dirname(BASE_DIR), "artifacts/file_generation/ttl=63d/output/zeus_custom_deployer.html")
    if os.path.exists(alt_file):
        with open(alt_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>ZEUS Deployer WebApp Ready</h1>")

@app.post("/api/mutate")
async def api_mutate(req: MutateRequest):
    repo_name = req.repo_name or generate_random_repo_name()
    admin_path = req.admin_path or generate_admin_path()
    uuid_str = req.uuid or generate_uuid()
    d1_name = req.d1_name or generate_d1_name()
    template = req.template_code or DEFAULT_TEMPLATE

    config = {
        "repo_name": repo_name,
        "admin_path": admin_path,
        "uuid": uuid_str,
        "d1_name": d1_name,
        "salt": secrets.token_hex(16)
    }

    obfuscated_code = obfuscate_worker_js(template, config)
    wrangler_code = generate_wrangler_toml(repo_name, d1_name, admin_path, uuid_str)
    readme_code = generate_cover_readme(repo_name)

    return {
        "status": "success",
        "repo_name": repo_name,
        "admin_path": admin_path,
        "uuid": uuid_str,
        "d1_name": d1_name,
        "worker_js": obfuscated_code,
        "wrangler_toml": wrangler_code,
        "readme_md": readme_code
    }

@app.post("/api/download-zip")
async def api_download_zip(req: MutateRequest):
    data = await api_mutate(req)
    repo_name = data["repo_name"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("_worker.js", data["worker_js"])
        zipf.writestr("wrangler.toml", data["wrangler_toml"])
        zipf.writestr("README.md", data["readme_md"])

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={repo_name}.zip"}
    )

@app.post("/api/deploy/cloudflare")
async def api_deploy_cloudflare(req: CloudflareDeployRequest):
    token = req.cf_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="کلید Cloudflare API Token الزامی است.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        # 1. Verify token
        verify_resp = await client.get("https://api.cloudflare.com/client/v4/user/tokens/verify", headers=headers)
        if verify_resp.status_code != 200:
            raise HTTPException(status_code=401, detail="توکن کلودفلر نامعتبر است یا دسترسی لازم را ندارد.")

        # 2. Get Account ID
        acc_resp = await client.get("https://api.cloudflare.com/client/v4/accounts", headers=headers)
        if acc_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="امکان دریافت لیست اکانت‌های کلودفلر وجود ندارد.")

        accounts = acc_resp.json().get("result", [])
        if not accounts:
            raise HTTPException(status_code=400, detail="هیچ حسابی برای این توکن پیدا نشد.")

        account_id = accounts[0]["id"]
        account_name = accounts[0]["name"]

        # 3. Generate unique polymorphic parameters
        script_name = req.custom_name or generate_random_repo_name()
        admin_path = req.custom_admin_path or generate_admin_path()
        uuid_str = generate_uuid()
        d1_name = generate_d1_name()
        salt = secrets.token_hex(16)

        # 4. Create D1 Database on Cloudflare
        d1_resp = await client.post(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database",
            headers=headers,
            json={"name": d1_name}
        )
        d1_id = "d1-auto-binding"
        if d1_resp.status_code in (200, 201):
            d1_data = d1_resp.json().get("result", {})
            d1_id = d1_data.get("uuid", d1_id)

        # 5. Obfuscate worker code
        config = {
            "repo_name": script_name,
            "admin_path": admin_path,
            "uuid": uuid_str,
            "d1_name": d1_name,
            "salt": salt
        }
        obfuscated_code = obfuscate_worker_js(DEFAULT_TEMPLATE, config)

        # 6. Upload worker with D1 bindings
        metadata = {
            "main_module": "_worker.js",
            "bindings": [
                {
                    "type": "d1",
                    "name": "DB",
                    "id": d1_id
                },
                {
                    "type": "plain_text",
                    "name": "ADMIN_PATH",
                    "text": admin_path
                },
                {
                    "type": "plain_text",
                    "name": "UUID",
                    "text": uuid_str
                }
            ],
            "compatibility_date": "2026-01-20",
            "compatibility_flags": ["nodejs_compat"]
        }

        files = {
            "metadata": (None, json.dumps(metadata), "application/json"),
            "_worker.js": ("_worker.js", obfuscated_code, "application/javascript+module")
        }
        upload_headers = {"Authorization": f"Bearer {token}"}

        upload_resp = await client.put(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}",
            headers=upload_headers,
            files=files
        )
        if upload_resp.status_code not in (200, 201):
            raise HTTPException(status_code=upload_resp.status_code, detail=f"خطا در استقرار ورکر: {upload_resp.text}")

        # 7. Enable workers.dev subdomain
        await client.post(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}/subdomain",
            headers=headers,
            json={"enabled": True}
        )

        # 8. Get Account subdomain
        sub_resp = await client.get(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/subdomain",
            headers=headers
        )
        workers_subdomain = "workers.dev"
        if sub_resp.status_code == 200:
            workers_subdomain = sub_resp.json().get("result", {}).get("subdomain", "workers.dev")

        live_domain = f"{script_name}.{workers_subdomain}.workers.dev"

        return {
            "status": "success",
            "account_name": account_name,
            "script_name": script_name,
            "d1_database": d1_name,
            "d1_id": d1_id,
            "admin_path": admin_path,
            "uuid": uuid_str,
            "panel_url": f"https://{live_domain}{admin_path}",
            "subscription_url": f"https://{live_domain}/sub/{uuid_str}",
            "live_url": f"https://{live_domain}"
        }

@app.post("/api/deploy/github")
async def api_deploy_github(req: GitHubDeployRequest):
    headers = {
        "Authorization": f"Bearer {req.token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Zeus-Custom-Deployer"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        create_resp = await client.post(
            "https://api.github.com/user/repos",
            headers=headers,
            json={
                "name": req.repo_name,
                "private": req.is_private,
                "description": "Automated telemetry pipeline and edge cache"
            }
        )
        if create_resp.status_code not in (200, 201):
            raise HTTPException(status_code=create_resp.status_code, detail=f"GitHub error: {create_resp.text}")

        repo_data = create_resp.json()
        owner = repo_data["owner"]["login"]

        async def commit_file(filename: str, content: str, msg: str):
            b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            return await client.put(
                f"https://api.github.com/repos/{owner}/{req.repo_name}/contents/{filename}",
                headers=headers,
                json={"message": msg, "content": b64_content}
            )

        await commit_file("_worker.js", req.worker_code, "feat: edge worker pipeline")
        await commit_file("wrangler.toml", req.wrangler_code, "chore: configuration")
        await commit_file("README.md", req.readme_code, "docs: initial documentation")

    return {
        "status": "success",
        "repo_url": f"https://github.com/{owner}/{req.repo_name}",
        "owner": owner,
        "repo_name": req.repo_name
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"[*] Starting ZEUS Custom Deployer on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
