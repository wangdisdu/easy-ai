from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
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
from app.service.tool_service import ToolService

router = APIRouter(prefix="/tool", tags=["tool"])
mcp_router = APIRouter(prefix="/mcp-server", tags=["mcp-server"])
service = ToolService(SnowflakeGenerator(settings.snowflake_worker_id))


# ── Builtin tools ──


@router.get("/builtin", response_model=Resp[list[BuiltinToolResp]])
def list_builtin_tools() -> Resp[list[BuiltinToolResp]]:
    return Resp(data=service.list_builtin_tools())


# ── Tool CRUD ──


@router.get("/page", response_model=PagedResp[ToolResp])
def page_tool(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    source: str | None = Query(default=None),
    tool_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[ToolResp]:
    data, total = service.page_tool(
        db=db,
        req=ToolPageReq(
            page_no=page_no,
            page_size=page_size,
            keyword=keyword,
            source=source,
            tool_status=tool_status,
        ),
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[ToolResp])
def create_tool(
    req: ToolCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[ToolResp]:
    return Resp(data=service.create_tool(db=db, req=req, req_ctx=req_ctx))


@router.get("/{tool_id}", response_model=Resp[ToolResp])
def get_tool(tool_id: str, db: Session = Depends(get_db)) -> Resp[ToolResp]:
    return Resp(data=service.get_tool_by_id(db=db, tool_id=int(tool_id)))


@router.put("/{tool_id}", response_model=Resp[ToolResp])
def update_tool(
    tool_id: str,
    req: ToolUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[ToolResp]:
    return Resp(data=service.update_tool(db=db, tool_id=int(tool_id), req=req, req_ctx=req_ctx))


@router.delete("/{tool_id}", response_model=Resp[bool])
def delete_tool(tool_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_tool(db=db, tool_id=int(tool_id))
    return Resp(data=True)


@router.post("/{tool_id}/enable", response_model=Resp[ToolResp])
def enable_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[ToolResp]:
    return Resp(
        data=service.toggle_tool_status(
            db=db, tool_id=int(tool_id), status="enabled", req_ctx=req_ctx
        )
    )


@router.post("/{tool_id}/disable", response_model=Resp[ToolResp])
def disable_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[ToolResp]:
    return Resp(
        data=service.toggle_tool_status(
            db=db, tool_id=int(tool_id), status="disabled", req_ctx=req_ctx
        )
    )


# ── MCP Server CRUD ──


@mcp_router.post("/discover", response_model=Resp[list[McpDiscoveredTool]])
def discover_mcp_tools(req: McpDiscoverReq) -> Resp[list[McpDiscoveredTool]]:
    return Resp(data=service.discover_mcp_tools(req))


@mcp_router.get("", response_model=Resp[list[McpServerResp]])
def list_mcp_servers(db: Session = Depends(get_db)) -> Resp[list[McpServerResp]]:
    return Resp(data=service.list_mcp_servers(db=db))


@mcp_router.post("", response_model=Resp[McpServerResp])
def create_mcp_server(
    req: McpServerCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[McpServerResp]:
    return Resp(data=service.create_mcp_server(db=db, req=req, req_ctx=req_ctx))


@mcp_router.get("/{server_id}", response_model=Resp[McpServerResp])
def get_mcp_server(server_id: str, db: Session = Depends(get_db)) -> Resp[McpServerResp]:
    return Resp(data=service.get_mcp_server_by_id(db=db, server_id=int(server_id)))


@mcp_router.put("/{server_id}", response_model=Resp[McpServerResp])
def update_mcp_server(
    server_id: str,
    req: McpServerUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[McpServerResp]:
    return Resp(
        data=service.update_mcp_server(db=db, server_id=int(server_id), req=req, req_ctx=req_ctx)
    )


@mcp_router.delete("/{server_id}", response_model=Resp[bool])
def delete_mcp_server(server_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_mcp_server(db=db, server_id=int(server_id))
    return Resp(data=True)
