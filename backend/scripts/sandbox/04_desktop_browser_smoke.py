"""桌面浏览器冒烟:
1) 确保「桌面(可视化)」沙盒镜像记录存在(供前端选择)
2) 起真实桌面沙盒 + 拉起桌面栈
3) headless 验 noVNC 的 WebSocket 经 OpenSandbox 代理能否升级 + 收到 RFB 握手
4) 打印一个 vnc.html URL,你直接浏览器打开就能看 Ubuntu(沙盒 ~30min 后自动回收)
"""

import sys
import time
from urllib.parse import urlparse

from websockets.sync.client import connect

from app.core.config import settings

settings.sandbox_enabled = True
settings.sandbox_server_url = "http://127.0.0.1:8090"
settings.sandbox_api_key = None

from app.app.sandbox.registry import get_sandbox_registry  # noqa: E402
from app.core.request_context import RequestContext  # noqa: E402
from app.core.snowflake import SnowflakeGenerator  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.model.sandbox_model import SandboxImageCreateReq  # noqa: E402
from app.service.sandbox_image_service import SandboxImageService  # noqa: E402

DESKTOP_IMAGE = "easy-ai/sandbox-desktop:latest"
NAME = "桌面(可视化)"

# 1) 镜像记录(幂等)
db = SessionLocal()
svc = SandboxImageService(SnowflakeGenerator(1))
existing = next((i for i in svc.list_enabled(db) if i.name == NAME), None)
if existing:
    print(f"[skip] 镜像记录已存在: {NAME} id={existing.id}")
else:
    ctx = RequestContext(user_id=1, request_time_ms=int(time.time() * 1000))
    r = svc.create_image(
        db,
        SandboxImageCreateReq(
            name=NAME, image=DESKTOP_IMAGE, description="noVNC 桌面,可视化沙盒", enabled=True
        ),
        ctx,
    )
    print(f"[ok] 已建镜像记录: {NAME} id={r.id} —— 前端「沙盒管理」可见,应用启用沙盒时可选")
db.close()

# 2) 起桌面沙盒 + 拉起桌面
reg = get_sandbox_registry()
SESSION = "desktop-browser-smoke"
APP = {"runtime_backend": "opensandbox", "sandbox": {"image": DESKTOP_IMAGE}}
b = reg.get_or_create(session_key=SESSION, app_config=APP)
print(f"[ok] 沙盒已创建 id={b.id}")
info = reg.desktop_endpoint(SESSION)
assert info and info.get("url"), f"desktop_endpoint 失败: {info}"
url = info["url"]
u = urlparse(url)
prefix = u.path.strip("/")
print(f"[ok] 代理 URL: {url}")

# 3) headless 验 WebSocket 升级 + RFB 握手(浏览器黑屏的根因就在这一步)
ws_url = f"ws://{u.netloc}/{prefix}/websockify"
ok = False
for _ in range(15):
    try:
        with connect(ws_url, subprotocols=["binary"], open_timeout=5) as ws:
            msg = ws.recv(timeout=5)
            data = msg if isinstance(msg, bytes) else msg.encode()
            if data[:3] == b"RFB":
                print(f"[PASS] WebSocket 升级成功,收到 VNC 握手: {data[:12]!r}")
                ok = True
                break
    except Exception as e:
        last = e
    time.sleep(2)
if not ok:
    print(f"[FAIL] WebSocket 未能拿到 RFB 握手 (ws_url={ws_url}); last={locals().get('last')}")

# 4) 给你浏览器直接打开的 URL(不 release,沙盒按 idle_timeout ~30min 自回收)
browser_url = f"{u.scheme}://{u.netloc}/{prefix}/vnc.html?autoconnect=true&resize=scale&path={prefix}/websockify"
print("\n================ 浏览器打开下面这个看 Ubuntu 桌面 ================")
print(browser_url)
print("================================================================")
print(f"用完手动清理:docker rm -f $(docker ps -q --filter 'name=sandbox-' )  或等 ~30min 自回收")
sys.exit(0 if ok else 1)
