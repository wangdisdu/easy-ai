"""沙盒实例管理 service 端到端:list / view / kill。"""
import sys, time, httpx
from app.core.config import settings
settings.sandbox_enabled = True
settings.sandbox_server_url = "http://127.0.0.1:8090"
settings.sandbox_api_key = None
from app.app.sandbox.registry import get_sandbox_registry  # noqa: E402
from app.service.sandbox_instance_service import SandboxInstanceService  # noqa: E402

reg = get_sandbox_registry()
svc = SandboxInstanceService()
fail = []
def ck(n, c, x=""):
    print(f"[{'PASS' if c else 'FAIL'}] {n} {x}")
    c or fail.append(n)

# 0) 起一个桌面沙盒
APP = {"runtime_backend": "opensandbox", "sandbox": {"image": "easy-ai/sandbox-desktop:latest"}}
SESSION = "inst-e2e"
b = reg.get_or_create(session_key=SESSION, app_config=APP)
real_id = b._sandbox.id  # OpenSandbox 真实 UUID;b.id 只是 session_key
print("created session=%s real=%s" % (SESSION, real_id))
reg.desktop_endpoint(SESSION)
time.sleep(3)

# 1) list 能看到
items = svc.list_instances()
print("list:", [(i.id[:8], i.status, (i.image or '')[:30]) for i in items])
ck("list_instances 能看到我创建的沙盒", any(i.id == real_id for i in items))
target = next((i for i in items if i.id == real_id), None)
assert target, "目标沙盒未在列表中"
ck("元数据含 image", "sandbox-desktop" in (target.image or ""), target.image or "")
ck("created_at 非空", bool(target.created_at), target.created_at)

# 2) view 拿到完整 URL,且 vnc.html 可达
view = svc.view_endpoint(real_id)
ck("view_endpoint ready", view.ready and view.url and view.url.startswith("http"), view.url)
if view.ready and view.url:
    ok = False
    for _ in range(8):
        try:
            r = httpx.get(f"{view.url.rstrip('/')}/vnc.html", timeout=5, follow_redirects=True)
            if r.status_code == 200 and "noVNC" in r.text:
                ok = True; break
        except Exception:
            pass
        time.sleep(1.5)
    ck("noVNC 可达", ok)

# 3) kill 后 list 不再看到
svc.kill_instance(real_id)
time.sleep(2)
items2 = svc.list_instances()
ck("kill 后从 list 消失", not any(i.id == real_id for i in items2))

print("\nRESULT:", "ALL PASS" if not fail else f"FAIL={fail}")
sys.exit(1 if fail else 0)
