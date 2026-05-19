"""端到端:真实桌面沙盒里验证 computer-use 工具真的驱动 xdotool/scrot。"""

import base64
import sys

from app.core.config import settings

settings.sandbox_enabled = True
settings.sandbox_server_url = "http://127.0.0.1:8090"
settings.sandbox_api_key = None

from app.app.computer_tools import build_computer_tools  # noqa: E402
from app.app.langchain_util import LangChainUtil  # noqa: E402
from app.app.sandbox.registry import get_sandbox_registry  # noqa: E402

reg = get_sandbox_registry()
SESSION = "cu-e2e"
APP = {"runtime_backend": "opensandbox", "sandbox": {"image": "easy-ai/sandbox-desktop:latest"}}
fail = []


def ck(n, c, extra=""):
    print(f"[{'PASS' if c else 'FAIL'}] {n} {extra}")
    c or fail.append(n)


b = reg.get_or_create(session_key=SESSION, app_config=APP)
print("sandbox id =", b.id)
# 拉起桌面栈(Xvfb 等)
reg.desktop_endpoint(SESSION)

tools = {t.name: t for t in build_computer_tools(session_key=SESSION, langchain_util=LangChainUtil())}
print("tools:", sorted(tools))
ck("8 个工具", len(tools) == 8)

# screenshot:应回传 [text, image_url] 且 base64 是合法 PNG
shot = tools["screenshot"].func()
img_ok = (
    isinstance(shot, list)
    and shot[1]["type"] == "image_url"
    and shot[1]["image_url"]["url"].startswith("data:image/png;base64,")
)
if img_ok:
    raw = base64.b64decode(shot[1]["image_url"]["url"].split(",", 1)[1])
    img_ok = raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) > 1000
ck("screenshot 返回合法 PNG", img_ok, f"{len(raw) if img_ok else '?'}B" if img_ok else str(shot)[:120])

# move_mouse → 用 xdotool getmouselocation 验证真的移动了
print(tools["move_mouse"].func(x=321, y=234))
loc = reg.exec_in_session(SESSION, "sh -lc 'DISPLAY=:1 xdotool getmouselocation --shell'")
ck("move_mouse 生效", "X=321" in (loc.output or "") and "Y=234" in (loc.output or ""), repr((loc.output or "")[:60]))

# type_text / press_key:xdotool 退出码 0 即注入成功(无焦点也不报错)
ck("type_text ok", tools["type_text"].func(text="hello 沙盒 $afe").startswith("已输入"))
ck("press_key ok", tools["press_key"].func(keys="ctrl+a").startswith("已按键"))
ck("press_key 拦非法", tools["press_key"].func(keys="rm -rf /").startswith("[computer] 非法"))
ck("click ok", tools["click"].func(x=200, y=200).startswith("已点击"))
ck("坐标越界拦截", tools["click"].func(x=999999, y=1).startswith("[computer] 坐标"))

# 沙盒不存在时优雅降级
ck(
    "无沙盒优雅降级",
    "沙盒尚未创建"
    in build_computer_tools(session_key="nope-xyz", langchain_util=LangChainUtil())[1].func(
        x=1, y=1
    ),
)

reg.release(SESSION)
print("\nRESULT:", "ALL PASS" if not fail else f"FAIL={fail}")
sys.exit(1 if fail else 0)
