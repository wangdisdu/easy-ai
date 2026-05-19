import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.mcp_client import discover_tools
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbMcpServer, TbTool
from app.model.tool_model import (
    BuiltinToolResp,
    McpDiscoveredTool,
    McpDiscoverReq,
    McpServerCreateReq,
    McpServerResp,
    McpServerUpdateReq,
    ToolCreateReq,
    ToolPageReq,
    ToolResp,
    ToolUpdateReq,
)

# 用户可创建的工具来源。'builtin' 不在内:它是 deepagents 框架内置工具
# (execute / write_file / edit_file)的治理记录,只由迁移种入、不走 CRUD。
VALID_SOURCES = {"mcp", "api"}
BUILTIN_SOURCE = "builtin"
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_TRANSPORTS = {"sse", "streamable_http"}
VALID_TOOL_STATUSES = {"enabled", "disabled"}

# ── 系统内置工具（硬编码，不入库） ──

BUILTIN_TOOLS: list[BuiltinToolResp] = [
    BuiltinToolResp(
        tool_name="ls",
        group="文件",
        description="列出指定目录下的文件和子目录",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要列出的目录路径"},
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归列出子目录",
                    "default": False,
                },
                "pattern": {
                    "type": "string",
                    "description": "文件名过滤模式，如 *.log、*.py",
                },
            },
            "required": ["path"],
        },
    ),
    BuiltinToolResp(
        tool_name="glob",
        group="文件",
        description="按 glob 模式匹配文件路径",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 匹配模式，如 **/*.py、src/**/*.vue",
                },
                "path": {
                    "type": "string",
                    "description": "搜索起始目录，省略时从工作区根目录开始",
                },
            },
            "required": ["pattern"],
        },
    ),
    BuiltinToolResp(
        tool_name="grep",
        group="文件",
        description="在文件内容中搜索匹配指定正则表达式的行",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "正则表达式搜索模式"},
                "path": {
                    "type": "string",
                    "description": "搜索路径（文件或目录），省略时从工作区根目录开始",
                },
                "include": {
                    "type": "string",
                    "description": "文件过滤 glob 模式，如 *.py、*.{ts,tsx}",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "匹配行前后显示的上下文行数",
                    "default": 0,
                },
            },
            "required": ["pattern"],
        },
    ),
    BuiltinToolResp(
        tool_name="read_file",
        group="文件",
        description="读取指定文件的内容",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要读取的文件路径"},
                "offset": {
                    "type": "integer",
                    "description": "起始行号，从 0 开始",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "最大读取行数",
                    "default": 2000,
                },
            },
            "required": ["path"],
        },
    ),
    BuiltinToolResp(
        tool_name="edit_file",
        group="文件",
        description="对已有文件进行局部文本替换",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要编辑的文件路径"},
                "old_text": {
                    "type": "string",
                    "description": "要被替换的原始文本，必须与文件中的内容精确匹配",
                },
                "new_text": {"type": "string", "description": "替换后的新文本"},
                "replace_all": {
                    "type": "boolean",
                    "description": "是否替换所有匹配项。为 false 时要求 old_text 在文件中唯一",
                    "default": False,
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    ),
    BuiltinToolResp(
        tool_name="write_file",
        group="文件",
        description="创建新文件或完整覆盖写入已有文件",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径，目录不存在时自动创建",
                },
                "content": {"type": "string", "description": "要写入的完整文件内容"},
            },
            "required": ["path", "content"],
        },
    ),
    BuiltinToolResp(
        tool_name="execute",
        group="沙盒",
        description="在隔离沙盒内执行 shell 命令(仅沙盒后端可用;高危,默认走 HITL 人工确认)",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"},
                "timeout": {
                    "type": "integer",
                    "description": "单条命令最长执行秒数,缺省按 mcp_tool_timeout_seconds(300)",
                },
            },
            "required": ["command"],
        },
    ),
    BuiltinToolResp(
        tool_name="remember",
        group="记忆",
        description="记下一条关于当前用户的长期事实或偏好，下次对话仍可读取（scope=user，仅限当前用户）",
        parameters={
            "type": "object",
            "properties": {
                "memory_key": {
                    "type": "string",
                    "description": "唯一键，dot 命名空间，如 language.preference、profile.email",
                },
                "memory_value": {
                    "type": "string",
                    "description": "纯文本短句，不要超过 300 字；已存在的 key 会被覆盖",
                },
            },
            "required": ["memory_key", "memory_value"],
        },
    ),
    BuiltinToolResp(
        tool_name="forget",
        group="记忆",
        description="删除一条之前记下的用户记忆（scope=user，仅限当前用户）",
        parameters={
            "type": "object",
            "properties": {
                "memory_key": {"type": "string", "description": "要删除的记忆键"},
            },
            "required": ["memory_key"],
        },
    ),
    BuiltinToolResp(
        tool_name="list_my_memories",
        group="记忆",
        description="查看当前用户已记下的全部长期记忆（key:value 列表）",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    # ── computer-use 桌面操控(仅可视化沙盒 + 应用勾选「允许 Agent 操控桌面」可用)──
    BuiltinToolResp(
        tool_name="screenshot",
        group="桌面操控",
        description="截取沙盒桌面当前画面并返回图片(多模态,需视觉模型);写类操作前先调一次看清界面",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    BuiltinToolResp(
        tool_name="click",
        group="桌面操控",
        description="在桌面坐标 (x,y) 单击左键(高危,默认走 HITL)",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "屏幕 X(0=左,1280 屏宽)"},
                "y": {"type": "integer", "description": "屏幕 Y(0=上,800 屏高)"},
            },
            "required": ["x", "y"],
        },
    ),
    BuiltinToolResp(
        tool_name="double_click",
        group="桌面操控",
        description="在 (x,y) 双击左键(打开图标/选中词,高危,默认 HITL)",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "屏幕 X"},
                "y": {"type": "integer", "description": "屏幕 Y"},
            },
            "required": ["x", "y"],
        },
    ),
    BuiltinToolResp(
        tool_name="right_click",
        group="桌面操控",
        description="在 (x,y) 单击右键(呼出上下文菜单,高危,默认 HITL)",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "屏幕 X"},
                "y": {"type": "integer", "description": "屏幕 Y"},
            },
            "required": ["x", "y"],
        },
    ),
    BuiltinToolResp(
        tool_name="move_mouse",
        group="桌面操控",
        description="把鼠标移到 (x,y),不点击(只读 hover,低风险)",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "屏幕 X"},
                "y": {"type": "integer", "description": "屏幕 Y"},
            },
            "required": ["x", "y"],
        },
    ),
    BuiltinToolResp(
        tool_name="scroll",
        group="桌面操控",
        description="在 (x,y) 滚动(高危,默认 HITL)",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "屏幕 X"},
                "y": {"type": "integer", "description": "屏幕 Y"},
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "滚动方向",
                },
                "amount": {"type": "integer", "description": "滚动次数 1-20"},
            },
            "required": ["x", "y"],
        },
    ),
    BuiltinToolResp(
        tool_name="type_text",
        group="桌面操控",
        description="在当前焦点处输入文本(先 click 聚焦目标输入框;ASCII+CJK 均可,高危,默认 HITL)",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要输入的文本(≤2000 字符)"},
            },
            "required": ["text"],
        },
    ),
    BuiltinToolResp(
        tool_name="press_key",
        group="桌面操控",
        description="按键或组合键(如 Return、Escape、ctrl+c、alt+Tab;高危,默认 HITL)",
        parameters={
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": "xdotool keysym;白名单只允许字母数字 + 和 _",
                },
            },
            "required": ["keys"],
        },
    ),
]


class ToolService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    # ── Builtin ──

    def list_builtin_tools(self) -> list[BuiltinToolResp]:
        return BUILTIN_TOOLS

    # ── MCP Server CRUD ──

    def create_mcp_server(
        self, db: Session, req: McpServerCreateReq, req_ctx: RequestContext
    ) -> McpServerResp:
        if req.transport not in VALID_TRANSPORTS:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid transport: {req.transport}")

        existing = db.scalars(
            select(TbMcpServer).where(TbMcpServer.server_name == req.server_name)
        ).first()
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "server_name already exists")

        now = req_ctx.request_time_ms
        entity = TbMcpServer(
            id=self._id_generator.next_id(),
            server_name=req.server_name,
            transport=req.transport,
            endpoint_url=req.endpoint_url,
            headers=json.dumps(req.headers, ensure_ascii=False) if req.headers else None,
            remark=req.remark,
            server_status="enabled",
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return McpServerResp.from_entity(entity)

    def list_mcp_servers(self, db: Session) -> list[McpServerResp]:
        rows = db.scalars(select(TbMcpServer).order_by(TbMcpServer.create_time.desc())).all()
        # batch load tool counts
        server_ids = [r.id for r in rows]
        counts: dict[int, int] = {}
        if server_ids:
            count_rows = db.execute(
                select(TbTool.mcp_server_id, func.count(TbTool.id))
                .where(TbTool.mcp_server_id.in_(server_ids))
                .group_by(TbTool.mcp_server_id)
            ).all()
            counts = {row[0]: row[1] for row in count_rows}
        return [McpServerResp.from_entity(r, counts.get(r.id, 0)) for r in rows]

    def get_mcp_server_by_id(self, db: Session, server_id: int) -> McpServerResp:
        entity = db.get(TbMcpServer, server_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "mcp server not found")
        tool_count = (
            db.scalar(select(func.count(TbTool.id)).where(TbTool.mcp_server_id == server_id)) or 0
        )
        return McpServerResp.from_entity(entity, tool_count)

    def update_mcp_server(
        self, db: Session, server_id: int, req: McpServerUpdateReq, req_ctx: RequestContext
    ) -> McpServerResp:
        entity = db.get(TbMcpServer, server_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "mcp server not found")

        if req.server_name is not None:
            dup = db.scalars(
                select(TbMcpServer).where(
                    TbMcpServer.server_name == req.server_name, TbMcpServer.id != server_id
                )
            ).first()
            if dup:
                raise ServiceError(ErrorCode.DATA_DUPLICATE, "server_name already exists")
            entity.server_name = req.server_name
        if req.transport is not None:
            if req.transport not in VALID_TRANSPORTS:
                raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid transport: {req.transport}")
            entity.transport = req.transport
        if req.endpoint_url is not None:
            entity.endpoint_url = req.endpoint_url
        if req.headers is not None:
            entity.headers = json.dumps(req.headers, ensure_ascii=False)
        if req.remark is not None:
            entity.remark = req.remark
        if req.server_status is not None:
            if req.server_status not in VALID_TOOL_STATUSES:
                raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid status: {req.server_status}")
            entity.server_status = req.server_status

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        tool_count = (
            db.scalar(select(func.count(TbTool.id)).where(TbTool.mcp_server_id == server_id)) or 0
        )
        return McpServerResp.from_entity(entity, tool_count)

    def delete_mcp_server(self, db: Session, server_id: int) -> None:
        entity = db.get(TbMcpServer, server_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "mcp server not found")
        db.query(TbTool).filter(TbTool.mcp_server_id == server_id).delete()
        db.delete(entity)
        db.commit()

    # ── Tool CRUD ──

    def create_tool(self, db: Session, req: ToolCreateReq, req_ctx: RequestContext) -> ToolResp:
        if req.source not in VALID_SOURCES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid source: {req.source}")
        if req.risk_level and req.risk_level not in VALID_RISK_LEVELS:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid risk_level: {req.risk_level}")

        if req.source == "mcp" and req.mcp_server_id:
            server = db.get(TbMcpServer, int(req.mcp_server_id))
            if not server:
                raise ServiceError(ErrorCode.DATA_NOT_FOUND, "mcp server not found")

        now = req_ctx.request_time_ms
        entity = TbTool(
            id=self._id_generator.next_id(),
            source=req.source,
            tool_name=req.tool_name,
            description=req.description,
            parameters=json.dumps(req.parameters, ensure_ascii=False),
            tool_group=req.tool_group,
            risk_level=req.risk_level or "low",
            tool_status="enabled",
            mcp_server_id=int(req.mcp_server_id) if req.mcp_server_id else None,
            api_config=(json.dumps(req.api_config, ensure_ascii=False) if req.api_config else None),
            hitl_timeout_seconds=req.hitl_timeout_seconds,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return ToolResp.from_entity(entity)

    def page_tool(self, db: Session, req: ToolPageReq) -> tuple[list[ToolResp], int]:
        stmt = select(TbTool)
        count_stmt = select(func.count(TbTool.id))

        conditions = []
        if req.keyword:
            kw = f"%{req.keyword}%"
            conditions.append(or_(TbTool.tool_name.like(kw), TbTool.description.like(kw)))
        if req.source:
            conditions.append(TbTool.source == req.source)
        if req.tool_status:
            conditions.append(TbTool.tool_status == req.tool_status)

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbTool.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [ToolResp.from_entity(row) for row in rows], total

    def get_tool_by_id(self, db: Session, tool_id: int) -> ToolResp:
        entity = db.get(TbTool, tool_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "tool not found")
        return ToolResp.from_entity(entity)

    def update_tool(
        self, db: Session, tool_id: int, req: ToolUpdateReq, req_ctx: RequestContext
    ) -> ToolResp:
        entity = db.get(TbTool, tool_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "tool not found")

        if req.tool_name is not None:
            entity.tool_name = req.tool_name
        if req.description is not None:
            entity.description = req.description
        if req.parameters is not None:
            entity.parameters = json.dumps(req.parameters, ensure_ascii=False)
        if req.tool_group is not None:
            entity.tool_group = req.tool_group
        if req.risk_level is not None:
            if req.risk_level not in VALID_RISK_LEVELS:
                raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid risk_level: {req.risk_level}")
            entity.risk_level = req.risk_level
        if req.api_config is not None:
            entity.api_config = json.dumps(req.api_config, ensure_ascii=False)
        if req.hitl_timeout_seconds is not None:
            entity.hitl_timeout_seconds = req.hitl_timeout_seconds

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return ToolResp.from_entity(entity)

    def delete_tool(self, db: Session, tool_id: int) -> None:
        entity = db.get(TbTool, tool_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "tool not found")
        mcp_server_id = entity.mcp_server_id
        db.delete(entity)
        db.flush()
        # auto-delete mcp server if no tools remain
        if mcp_server_id:
            remaining = (
                db.scalar(
                    select(func.count(TbTool.id)).where(TbTool.mcp_server_id == mcp_server_id)
                )
                or 0
            )
            if remaining == 0:
                server = db.get(TbMcpServer, mcp_server_id)
                if server:
                    db.delete(server)
        db.commit()

    # ── MCP Discover ──

    def discover_mcp_tools(self, req: McpDiscoverReq) -> list[McpDiscoveredTool]:
        if req.transport not in VALID_TRANSPORTS:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid transport: {req.transport}")
        headers: dict[str, str] | None = None
        if req.headers:
            headers = {k: str(v) for k, v in req.headers.items()}
        try:
            tools = discover_tools(
                transport=req.transport,
                url=req.endpoint_url,
                headers=headers,
            )
        except BaseException as e:
            cause = e
            while isinstance(cause, BaseExceptionGroup) and cause.exceptions:
                cause = cause.exceptions[0]
            raise ServiceError(ErrorCode.BAD_REQUEST, f"failed to connect: {cause}") from e
        return [
            McpDiscoveredTool(name=t.name, description=t.description, parameters=t.parameters)
            for t in tools
        ]

    def toggle_tool_status(
        self, db: Session, tool_id: int, status: str, req_ctx: RequestContext
    ) -> ToolResp:
        if status not in VALID_TOOL_STATUSES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid status: {status}")
        entity = db.get(TbTool, tool_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "tool not found")
        entity.tool_status = status
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return ToolResp.from_entity(entity)
