"""computer-use 工具:让 Agent 看/操控可视化沙盒的 Ubuntu 桌面(Tier 3)。

设计:
- 工具调用时按 session_key 找该会话沙盒,经 execd 跑 scrot/xdotool(DISPLAY=:1)。
- 沙盒不存在(还没触发任何沙盒工具)→ 返回提示串,模型自愈/告知用户。
- 文本/按键经 base64 传入沙盒再解码,杜绝 shell 转义与注入。
- screenshot 回传图片内容块(data URL),供视觉模型直接看;需模型支持
  tool_result 图片(如 Claude via LiteLLM)。非视觉模型则只能盲操(用户仍可在
  noVNC 面板看到画面)。
- click/type/key 等写类工具由 §5 PolicyMiddleware 治理(迁移 0017 以
  source='builtin' 种入 tb_tool,高危走 HITL),本模块不重复鉴权。

详见 docs/sandbox-design.md §9.5。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.app.langchain_util import LangChainUtil

logger = logging.getLogger(__name__)

_DISPLAY = "DISPLAY=:1"
# xdotool key 允许的 keysym/组合:字母数字、+、_、常见特殊键名。防注入。
_KEY_RE = re.compile(r"^[A-Za-z0-9_+]+(?: [A-Za-z0-9_+]+)*$")
_MAX_COORD = 10000


def _err(msg: str) -> str:
    return f"[computer] {msg}"


def build_computer_tools(*, session_key: str | None, langchain_util: LangChainUtil) -> list[Any]:
    """每次 agent 启动按 run-context 闭包出 computer-use 工具。

    session_key 为空(无 thread)→ 返回空列表,不挂载。
    """
    if not session_key:
        return []

    def _run(command: str, timeout: int = 60) -> Any | None:
        # 延迟导入,避免非沙盒部署加载 opensandbox。
        from app.app.sandbox import get_sandbox_registry

        return get_sandbox_registry().exec_in_session(session_key, command, timeout=timeout)

    def _screenshot() -> Any:
        res = _run(
            "sh -lc 'DISPLAY=:1 scrot -z -o /tmp/_cu.png && base64 /tmp/_cu.png | tr -d \"\\n\"'",
            timeout=30,
        )
        if res is None:
            return _err("沙盒尚未创建:先触发一次沙盒工具(如 execute)再截图")
        b64 = (res.output or "").strip()
        if res.exit_code != 0 or not b64:
            return _err(f"截图失败 exit={res.exit_code}: {b64[:200]}")
        # 多模态工具返回:文本 + 图片内容块(data URL)
        return [
            {"type": "text", "text": "当前桌面截图(1280x800):"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            },
        ]

    def _xdo(args: str, ok_msg: str, timeout: int = 20) -> str:
        res = _run(f"sh -lc '{_DISPLAY} xdotool {args}'", timeout=timeout)
        if res is None:
            return _err("沙盒尚未创建:先触发一次沙盒工具(如 execute)")
        if res.exit_code != 0:
            return _err(f"操作失败 exit={res.exit_code}: {(res.output or '')[:200]}")
        return ok_msg

    def _coord_ok(x: int, y: int) -> bool:
        return 0 <= x <= _MAX_COORD and 0 <= y <= _MAX_COORD

    def _click(x: int, y: int, button: int = 1) -> str:
        if not _coord_ok(x, y):
            return _err("坐标越界")
        return _xdo(
            f"mousemove {int(x)} {int(y)} click {int(button)}",
            f"已点击 ({x},{y}) button={button}",
        )

    def _double_click(x: int, y: int) -> str:
        if not _coord_ok(x, y):
            return _err("坐标越界")
        return _xdo(
            f"mousemove {int(x)} {int(y)} click --repeat 2 --delay 80 1",
            f"已双击 ({x},{y})",
        )

    def _right_click(x: int, y: int) -> str:
        return _click(x, y, button=3)

    def _move(x: int, y: int) -> str:
        if not _coord_ok(x, y):
            return _err("坐标越界")
        return _xdo(f"mousemove {int(x)} {int(y)}", f"已移动到 ({x},{y})")

    def _scroll(x: int, y: int, direction: str = "down", amount: int = 3) -> str:
        if not _coord_ok(x, y):
            return _err("坐标越界")
        btn = 5 if direction == "down" else 4
        amount = max(1, min(int(amount), 20))
        return _xdo(
            f"mousemove {int(x)} {int(y)} click --repeat {amount} {btn}",
            f"已滚动 {direction} x{amount} @({x},{y})",
        )

    def _type_text(text: str) -> str:
        if not text:
            return _err("text 为空")
        if len(text) > 2000:
            return _err("文本过长(>2000),请分段输入")
        # xdotool type 对多字节(中文)直接报错;改用 Unicode keysym 逐字符
        # key 注入(ASCII+CJK 都可靠)。token 仅 [A-Za-z0-9],无需引号/防注入。
        special = {" ": "space", "\n": "Return", "\t": "Tab"}
        syms: list[str] = []
        for ch in text:
            cp = ord(ch)
            if ch in special:
                syms.append(special[ch])
            elif cp > 0xFFFF:
                return _err(f"暂不支持的字符 U+{cp:X}(如表情);请用 BMP 文本")
            else:
                syms.append(f"U{cp:04X}")
        cmd = f"sh -lc '{_DISPLAY} xdotool key --delay 15 -- {' '.join(syms)}'"
        res = _run(cmd, timeout=30)
        if res is None:
            return _err("沙盒尚未创建")
        if res.exit_code != 0:
            return _err(f"输入失败 exit={res.exit_code}: {(res.output or '')[:200]}")
        return f"已输入 {len(text)} 字符"

    def _key(keys: str) -> str:
        keys = (keys or "").strip()
        if not _KEY_RE.match(keys):
            return _err("非法按键;示例:Return / ctrl+c / alt+Tab / Escape")
        return _xdo(f"key --clearmodifiers {keys}", f"已按键 {keys}")

    int_xy = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "屏幕 X(0=左,1280 屏宽)"},
            "y": {"type": "integer", "description": "屏幕 Y(0=上,800 屏高)"},
        },
        "required": ["x", "y"],
    }

    bt = langchain_util.build_structured_tool
    return [
        bt(
            name="screenshot",
            description="截取沙盒桌面当前画面并返回图片。每次要操作前先截图看清界面再决定坐标。",
            schema={"type": "object", "properties": {}, "required": []},
            func=_screenshot,
        ),
        bt(
            name="click",
            description="在桌面坐标 (x,y) 单击左键。坐标以最近一次 screenshot 为准。",
            schema=int_xy,
            func=_click,
        ),
        bt(
            name="double_click",
            description="在 (x,y) 双击左键(打开图标/选中词)。",
            schema=int_xy,
            func=_double_click,
        ),
        bt(
            name="right_click",
            description="在 (x,y) 单击右键(呼出上下文菜单)。",
            schema=int_xy,
            func=_right_click,
        ),
        bt(
            name="move_mouse",
            description="把鼠标移到 (x,y),不点击(用于 hover)。",
            schema=int_xy,
            func=_move,
        ),
        bt(
            name="scroll",
            description="在 (x,y) 滚动。direction=up/down,amount=次数(1-20)。",
            schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
            func=_scroll,
        ),
        bt(
            name="type_text",
            description="在当前焦点处输入文本(先 click 聚焦目标输入框)。",
            schema={
                "type": "object",
                "properties": {"text": {"type": "string", "description": "要输入的文本"}},
                "required": ["text"],
            },
            func=_type_text,
        ),
        bt(
            name="press_key",
            description="按键或组合键。示例:Return、Escape、ctrl+c、alt+Tab、ctrl+shift+t。",
            schema={
                "type": "object",
                "properties": {"keys": {"type": "string", "description": "xdotool keysym"}},
                "required": ["keys"],
            },
            func=_key,
        ),
    ]
