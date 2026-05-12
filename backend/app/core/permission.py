"""系统权限码定义。

设计原则：
- 每个业务模块按"定义层 vs 运行层"二分：`*:edit` 管资源 CRUD，`*:publish` / `*:control`
  管上线下线、启用禁用、ACL 等运行行为。
- 查看默认隐含：拥有该模块任一子权限即可读取列表/详情，纯读操作不单独占权限码。
- 角色 `permissions` 存通配 `*` 时视为超级管理员，拥有所有权限码。
"""

from __future__ import annotations

from dataclasses import dataclass

PERMISSION_WILDCARD = "*"


@dataclass(frozen=True)
class PermissionDef:
    code: str
    label: str
    group: str
    description: str


# 模块分组顺序即前端展示顺序
PERMISSION_DEFS: list[PermissionDef] = [
    PermissionDef(
        code="app:edit",
        label="应用编辑",
        group="应用工厂",
        description="应用与应用分类的创建、编辑、删除",
    ),
    PermissionDef(
        code="app:publish",
        label="应用发布",
        group="应用工厂",
        description="应用版本发布与下线",
    ),
    PermissionDef(
        code="skill:edit",
        label="技能编辑",
        group="技能管理",
        description="技能的创建、编辑、删除",
    ),
    PermissionDef(
        code="skill:publish",
        label="技能发布",
        group="技能管理",
        description="技能发布、启用、禁用",
    ),
    PermissionDef(
        code="tool:edit",
        label="工具编辑",
        group="工具管理",
        description="MCP Server 与工具的创建、编辑、删除",
    ),
    PermissionDef(
        code="tool:control",
        label="工具运行控制",
        group="工具管理",
        description="工具启用、禁用与 ACL 策略配置",
    ),
    PermissionDef(
        code="kb:edit",
        label="知识库编辑",
        group="知识库管理",
        description="知识库与文档的创建、编辑、删除",
    ),
    PermissionDef(
        code="kb:publish",
        label="知识库发布",
        group="知识库管理",
        description="知识库上线、下线、索引重建",
    ),
    PermissionDef(
        code="system:llm",
        label="LLM 配置",
        group="系统配置",
        description="LLM 提供商与模型管理",
    ),
    PermissionDef(
        code="system:setting",
        label="系统设置",
        group="系统配置",
        description="系统全局设置与初始化数据",
    ),
    PermissionDef(
        code="permission:user",
        label="用户管理",
        group="权限管理",
        description="用户与用户组的创建、编辑、删除及成员维护",
    ),
    PermissionDef(
        code="permission:role",
        label="角色管理",
        group="权限管理",
        description="角色及其授权关系管理",
    ),
]


ALL_PERMISSION_CODES: frozenset[str] = frozenset(p.code for p in PERMISSION_DEFS)


def has_permission(granted: list[str] | None, required: str) -> bool:
    """判断角色权限列表是否覆盖 required 权限码；持有 `*` 即视为拥有全部权限。"""
    if not granted:
        return False
    if PERMISSION_WILDCARD in granted:
        return True
    return required in granted
