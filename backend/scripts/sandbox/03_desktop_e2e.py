"""端到端:真实 registry 创建桌面沙盒 → desktop_endpoint 拉起桌面 + 签名 URL → 验证 noVNC 可达。"""

import sys
import time

import httpx

from app.core.config import settings

settings.sandbox_enabled = True
settings.sandbox_server_url = "http://127.0.0.1:8090"
settings.sandbox_api_key = None

from app.app.sandbox.registry import get_sandbox_registry  # noqa: E402

reg = get_sandbox_registry()
APP = {"runtime_backend": "opensandbox", "sandbox": {"image": "easy-ai/sandbox-desktop:latest"}}
SESSION = "desktop-e2e"
fail = []


def ck(n, c, extra=""):
    print(f"[{'PASS' if c else 'FAIL'}] {n} {extra}")
    c or fail.append(n)


b = reg.get_or_create(session_key=SESSION, app_config=APP)
print("sandbox id =", b.id)
# 沙盒先确保活着
r = b.execute("echo ready && command -v websockify")
ck("sandbox alive + desktop image", r.exit_code == 0 and "websockify" in r.output, repr(r.output[:60]))

info = reg.desktop_endpoint(SESSION)
ck("desktop_endpoint returns url", bool(info and info.get("url")), str(info)[:120] if info else "None")

if info and info.get("url"):
    base = info["url"].rstrip("/")
    headers = info.get("headers") or {}
    vnc = f"{base}/vnc.html"
    # 桌面栈刚拉起,给 Xvfb/websockify 一点时间
    ok = False
    for _ in range(15):
        try:
            resp = httpx.get(vnc, headers=headers, timeout=5, follow_redirects=True)
            if resp.status_code == 200 and "noVNC" in resp.text:
                ok = True
                break
        except Exception:
            pass
        time.sleep(2)
    ck("noVNC web reachable via signed url", ok, vnc)

reg.release(SESSION)
print("\nRESULT:", "ALL PASS" if not fail else f"FAIL={fail}")
sys.exit(1 if fail else 0)
