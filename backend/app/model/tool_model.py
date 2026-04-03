from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.db.schema import TbMcpServer, TbTool

# ── Builtin tool definition ──


class BuiltinToolResp(BaseModel):
    """系统内置工具（不入库，硬编码）"""

    source: str = "builtin"
    tool_name: str
    description: str
    parameters: dict


# ── MCP Server ──


class McpServerCreateReq(BaseModel):
    server_name: str = Field(min_length=1, max_length=255)
    transport: str = Field(min_length=1, max_length=255)
    endpoint_url: str = Field(min_length=1)
    headers: dict | None = Field(default=None)
    remark: str | None = Field(default=None)


class McpServerUpdateReq(BaseModel):
    server_name: str | None = Field(default=None, max_length=255)
    transport: str | None = Field(default=None, max_length=255)
    endpoint_url: str | None = Field(default=None)
    headers: dict | None = Field(default=None)
    remark: str | None = Field(default=None)
    server_status: str | None = Field(default=None, max_length=255)


class McpDiscoverReq(BaseModel):
    transport: str = Field(min_length=1, max_length=255)
    endpoint_url: str = Field(min_length=1)
    headers: dict | None = Field(default=None)


class McpDiscoveredTool(BaseModel):
    name: str
    description: str
    parameters: dict


class McpServerResp(BaseModel):
    id: str
    server_name: str
    transport: str
    endpoint_url: str
    headers: dict | None = None
    remark: str | None = None
    server_status: str
    tool_count: int = 0
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbMcpServer, tool_count: int = 0) -> McpServerResp:
        headers = None
        if entity.headers:
            try:
                headers = json.loads(entity.headers)
            except (json.JSONDecodeError, TypeError):
                headers = None
        return cls(
            id=str(entity.id),
            server_name=entity.server_name,
            transport=entity.transport,
            endpoint_url=entity.endpoint_url,
            headers=headers,
            remark=entity.remark,
            server_status=entity.server_status,
            tool_count=tool_count,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


# ── Tool ──


class ToolCreateReq(BaseModel):
    source: str = Field(min_length=1, max_length=255)
    tool_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)
    tool_group: str | None = Field(default=None, max_length=255)
    risk_level: str | None = Field(default="low", max_length=255)
    mcp_server_id: str | None = Field(default=None)
    api_config: dict | None = Field(default=None)


class ToolUpdateReq(BaseModel):
    tool_name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None)
    parameters: dict | None = Field(default=None)
    tool_group: str | None = Field(default=None, max_length=255)
    risk_level: str | None = Field(default=None, max_length=255)
    api_config: dict | None = Field(default=None)


class ToolPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=255)
    tool_status: str | None = Field(default=None, max_length=255)


class ToolResp(BaseModel):
    id: str
    source: str
    tool_name: str
    description: str
    parameters: dict
    tool_group: str | None = None
    risk_level: str | None = None
    tool_status: str
    mcp_server_id: str | None = None
    api_config: dict | None = None
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbTool) -> ToolResp:
        parameters: dict = {}
        if entity.parameters:
            try:
                parameters = json.loads(entity.parameters)
            except (json.JSONDecodeError, TypeError):
                parameters = {}
        api_config = None
        if entity.api_config:
            try:
                api_config = json.loads(entity.api_config)
            except (json.JSONDecodeError, TypeError):
                api_config = None
        return cls(
            id=str(entity.id),
            source=entity.source,
            tool_name=entity.tool_name,
            description=entity.description,
            parameters=parameters,
            tool_group=entity.tool_group,
            risk_level=entity.risk_level,
            tool_status=entity.tool_status,
            mcp_server_id=str(entity.mcp_server_id) if entity.mcp_server_id else None,
            api_config=api_config,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )
