from sqlalchemy import (
    BigInteger,
    Float,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TbUser(Base):
    __tablename__ = "tb_user"
    __table_args__ = (UniqueConstraint("account", name="uk_tb_user_account"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account: Mapped[str] = mapped_column(String(255), nullable=False)
    passwd: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbUserGroup(Base):
    __tablename__ = "tb_user_group"
    __table_args__ = (UniqueConstraint("code", name="uk_tb_user_group_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbUserGroupMember(Base):
    __tablename__ = "tb_user_group_member"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uk_tb_user_group_member_user_group"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbRole(Base):
    __tablename__ = "tb_role"
    __table_args__ = (UniqueConstraint("code", name="uk_tb_role_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    permissions: Mapped[str] = mapped_column(Text, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbUserRole(Base):
    __tablename__ = "tb_user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uk_tb_user_role_user_role"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbMcpServer(Base):
    __tablename__ = "tb_mcp_server"
    __table_args__ = (UniqueConstraint("server_name", name="uk_tb_mcp_server_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    server_name: Mapped[str] = mapped_column(String(255), nullable=False)
    transport: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    server_status: Mapped[str] = mapped_column(String(255), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbTool(Base):
    __tablename__ = "tb_tool"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[str] = mapped_column(Text, nullable=False)
    tool_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool_status: Mapped[str] = mapped_column(String(255), nullable=False)
    mcp_server_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    api_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    # HITL 超时秒数；NULL 走 settings.hitl_timeout_seconds（默认 300）；超时按 reject 续跑。
    hitl_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbAppCategory(Base):
    __tablename__ = "tb_app_category"
    __table_args__ = (UniqueConstraint("code", name="uk_tb_app_category_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


# 应用分类 — 目标（app / skill）多对多关系表
# target_type: 'app' | 'skill'
class TbAppCategoryRel(Base):
    __tablename__ = "tb_app_category_rel"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "target_type",
            "target_id",
            name="uk_tb_app_category_rel_uniq",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbSkill(Base):
    __tablename__ = "tb_skill"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    skill_status: Mapped[str] = mapped_column(String(255), nullable=False)
    current_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbSkillTool(Base):
    __tablename__ = "tb_skill_tool"
    __table_args__ = (
        UniqueConstraint(
            "skill_id", "tool_source", "tool_name", name="uk_tb_skill_tool_skill_source_name"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_source: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbSkillFile(Base):
    """技能捆绑文件:references / scripts / templates / assets 四类。

    rel_path 形如 `references/usage.md` / `scripts/gen.py`,首段决定 kind。
    在 SkillService._sync_skill_files 中强校验路径合法性(无 .. / 绝对路径)。
    """

    __tablename__ = "tb_skill_file"
    __table_args__ = (UniqueConstraint("skill_id", "rel_path", name="uk_tb_skill_file_skill_path"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rel_path: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    executable: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbSkillVersion(Base):
    __tablename__ = "tb_skill_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[str] = mapped_column(String(255), nullable=False)
    version_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbLlmProvider(Base):
    __tablename__ = "tb_llm_provider"
    __table_args__ = (UniqueConstraint("name", name="uk_tb_llm_provider_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    last_check: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbLlmModel(Base):
    __tablename__ = "tb_llm_model"
    __table_args__ = (
        UniqueConstraint("provider_id", "model", name="uk_tb_llm_model_provider_model"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    model_type: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    # 模型最大输入 token 数；缺省时摘要中间件会走 170k 兜底，
    # 配上后按 fraction 触发（例如 32k 模型在 ~27k 时触发摘要）。
    max_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbApp(Base):
    __tablename__ = "tb_app"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_type: Mapped[str] = mapped_column(String(255), nullable=False)
    app_status: Mapped[str] = mapped_column(String(255), nullable=False)
    app_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    rate_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    enable_log: Mapped[int] = mapped_column(Integer, nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Flowise chatflow uuid，仅 app_type=agent_flow 时写入
    flowise_chatflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbAppTool(Base):
    __tablename__ = "tb_app_tool"
    __table_args__ = (UniqueConstraint("app_id", "tool_id", name="uk_tb_app_tool_app_tool"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbAppSkill(Base):
    __tablename__ = "tb_app_skill"
    __table_args__ = (UniqueConstraint("app_id", "skill_id", name="uk_tb_app_skill_app_skill"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbAppVersion(Base):
    __tablename__ = "tb_app_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[str] = mapped_column(String(255), nullable=False)
    version_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbAppLog(Base):
    __tablename__ = "tb_app_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    app_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_type: Mapped[str] = mapped_column(String(255), nullable=False)
    request_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[int] = mapped_column(Integer, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbConversation(Base):
    __tablename__ = "tb_conversation"
    __table_args__ = (UniqueConstraint("thread_id", name="uk_tb_conversation_thread_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # LangGraph checkpoint 线程标识；首次真实调用时落地 str(id)，之后不变。
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # active / degraded / purged，checkpoint 生命周期独立于业务消息。
    checkpoint_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbConversationMessage(Base):
    __tablename__ = "tb_conversation_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbSessionAudit(Base):
    """会话级审计事件（checkpoint 重建/清理等），为后续 Policy 层审计流预留。"""

    __tablename__ = "tb_session_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TbToolPolicy(Base):
    """工具策略规则集。一行 = 一条规则；版本演化用行级软改（superseded_by_id）。"""

    __tablename__ = "tb_tool_policy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tool_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    # action: 'deny' / 'allow' / 'require_hitl'
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    # when_ast: JSON 文本，结构见 tool-approval-and-acl-design.md §5.1
    when_ast: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # mode: 'active' / 'shadow'
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="shadow")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 当前版本 NULL；历史版本指向取代它的新版本 id
    superseded_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbToolAudit(Base):
    """工具治理决策事件流（append-only），与 tb_session_audit 并列。"""

    __tablename__ = "tb_tool_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # event_type: tool_invoked / policy_denied / hitl_required /
    #   hitl_confirmed / hitl_modified / hitl_rejected / hitl_timeout /
    #   policy_modified
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    app_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 参数快照（JSON），入库前过 PII 脱敏
    parameters_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_rule_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TbMemory(Base):
    """长期记忆 KV：scope=user / app；agent 写工具或人工写都落这张表。"""

    __tablename__ = "tb_memory"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "memory_key", name="uk_tb_memory_scope_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user' | 'app'
    scope_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 写入者（人工 API / agent 工具调用时的当前 user）；admin 后台批量任务可为 NULL
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_key: Mapped[str] = mapped_column(String(255), nullable=False)
    memory_value: Mapped[str] = mapped_column(Text, nullable=False)
    # source: 'user_explicit' / 'agent_learned' / 'admin_set'
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbMemoryAudit(Base):
    """记忆变更事件流（append-only），与 tb_tool_audit / tb_session_audit 并列。"""

    __tablename__ = "tb_memory_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # event_type: 'remembered' / 'updated' / 'forgotten' / 'admin_purged'
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_key: Mapped[str] = mapped_column(String(255), nullable=False)
    memory_value_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_value_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    app_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)


# ── 知识库(v2 纯组织层, 详见 docs/knowledge-v2-design.md)──
# 向量化字段(embedding/chunk/ragflow_dataset 等)已迁至 tb_rag_dataset。
class TbKb(Base):
    __tablename__ = "tb_kb"
    __table_args__ = (UniqueConstraint("code", name="uk_tb_kb_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbKbDocument(Base):
    __tablename__ = "tb_kb_document"
    __table_args__ = (UniqueConstraint("kb_id", "name", name="uk_tb_kb_document_kb_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # PDF / DOCX / XLSX / MD / TXT / CSV / JSON / IMG / API / DB
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # easy-ai blob 存储相对路径; easy-ai 为文档真相源, 原文存此
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 树形分类节点 id(tb_kb_category.id); 0 = 未分类(直挂知识库根)。
    # 纯 easy-ai 侧元数据, 不参与 RAGFlow 建模。
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # file / ones / api_pull / api_push / confluence
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # connector 私有字段(filePath / sourceUrl / syncSchedule 等), JSON 字符串
    source_meta: Mapped[str | None] = mapped_column(Text, nullable=True)
    ragflow_doc_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 文档所属 RAG 库(tb_rag_dataset.id); 由分类映射推导固化, 未映射时为空
    rag_dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # not_mapped / pending / parsing / done / error —— 向量化(RAGFlow 侧)状态
    vectorize_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_mapped")
    chunks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 解析进度元数据,由 _sync_doc_status 从 RAGFlow document.progress/process_*
    # 字段回填,前端用来在 parsing 状态下展示百分比 + 已耗时 + RAGFlow 阶段提示
    parse_progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    parse_begin_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    parse_duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    parse_progress_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbKbCategory(Base):
    """知识库内文档分类(树形, 单归属)。

    纯 easy-ai 侧组织维度, RAGFlow 完全不感知。约定:
    - ``parent_id = 0`` 表示挂在知识库根下
    - ``id_path`` 物化路径 ``/<id>/<id>/...`` 以自身 id 结尾(含前后斜杠),
      子树查询用 ``id_path LIKE '<父path>%'``, 级联删除同理
    - ``level`` 深度, 根级 = 1, 上限见 KbCategoryService.MAX_DEPTH
    - 同级(同 kb_id + parent_id)下 name 唯一
    """

    __tablename__ = "tb_kb_category"
    __table_args__ = (
        UniqueConstraint("kb_id", "parent_id", "name", name="uk_tb_kb_category_sibling"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    id_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


# ── RAG 库(对应 RAGFlow Dataset, 持有 embedding/分块配置)──
class TbRagDataset(Base):
    __tablename__ = "tb_rag_dataset"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 对应 RAGFlow Dataset ID; 创建中为空
    ragflow_dataset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    # naive / qa / manual / book / table / laws, 对齐 RAGFlow chunk_method
    chunk_method: Mapped[str] = mapped_column(String(64), nullable=False)
    # RAGFlow parser_config, 存 JSON 字符串
    parser_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 缓存值, 由向量化 worker 定时回填
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # creating / ready / syncing / error
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="creating")
    last_synced_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


# ── 分类 → RAG 库 映射(N:1, category_id 唯一保证互斥)──
class TbKbCategoryMapping(Base):
    __tablename__ = "tb_kb_category_mapping"
    __table_args__ = (UniqueConstraint("category_id", name="uk_tb_kb_category_mapping_category"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # tb_kb_category.id —— 一个分类只能映射一个 RAG 库
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rag_dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # active / syncing / error
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


# ── 同步日志(知识集成 / 知识向量化)──
class TbSyncLog(Base):
    __tablename__ = "tb_sync_log"
    __table_args__ = (Index("ix_tb_sync_log_type_time", "log_type", "create_time"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # integration(知识集成) / vectorization(知识向量化)
    log_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 来源方式: file / ones / api_pull / api_push / vectorize 等
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_kb_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    docs_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # success / failed / partial / processing
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbSystemSetting(Base):
    """平台级配置 KV。key 命名空间见 docs/knowledge-rag-impl-plan.md §4 Step 1:
    ai.default.embedding_model_id / ai.default.rerank_model_id / ...
    所有 value 都按字符串落盘,语义由上层 service 决定(model_id 也存字符串)。"""

    __tablename__ = "tb_system_setting"

    setting_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    setting_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbSandboxImage(Base):
    """沙盒镜像目录(平台级)。Agent 应用在 ``app_config.sandbox.image_id``
    里从中选一个作为隔离执行环境的镜像;未选则用 ``is_default`` 的那条。
    详见 docs/sandbox-design.md §7。"""

    __tablename__ = "tb_sandbox_image"
    __table_args__ = (UniqueConstraint("name", name="uk_tb_sandbox_image_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    image: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 默认资源画像,透传 OpenSandbox create(resource=...);空=不限制
    cpu: Mapped[str | None] = mapped_column(String(64), nullable=True)
    memory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbIntegration(Base):
    """应用集成主表。

    对外开放 AI 能力的网关元数据。`status` 仅 active/disabled 两态;
    `quota` / `rate_limit` / `timeout` 三态:NULL=继承全局默认,0=不限,>0=具体值。
    详见 docs/application-integration-design.md §3.1。
    """

    __tablename__ = "tb_integration"
    __table_args__ = (
        UniqueConstraint("name", name="uk_tb_integration_name"),
        Index("idx_tb_integration_status", "status", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout: Mapped[int | None] = mapped_column(Integer, nullable=True)
    whitelist: Mapped[str | None] = mapped_column(Text, nullable=True)
    expire_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbIntegrationKey(Base):
    """集成 API Key。

    `key_hash` = SHA-256(plaintext),全局唯一,不存明文;`key_prefix`+`key_suffix`
    用于列表显示拼出 `sk-prod-9f3****xY2k`。`rate_limit` NULL=继承 Integration 级。
    """

    __tablename__ = "tb_integration_key"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uk_tb_integration_key_hash"),
        Index("idx_tb_integration_key_intg", "integration_id", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    integration_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_suffix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_used_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    revoked_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbIntegrationApp(Base):
    """集成与应用的绑定关系。

    `app_type` 进主键以避免跨表 ID 冲突:P1 的 kb_push 指向 tb_knowledge_base 而非 tb_app。
    """

    __tablename__ = "tb_integration_app"
    __table_args__ = (
        PrimaryKeyConstraint("integration_id", "app_type", "app_id", name="pk_tb_integration_app"),
        Index("idx_tb_integration_app_lookup", "app_type", "app_id"),
    )

    integration_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    app_type: Mapped[str] = mapped_column(String(32), nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TbIntegrationQuotaDay(Base):
    """日配额计数持久化。

    内存限流的 day_count 每分钟批量 UPSERT 到此表;进程重启后从此表 hydrate,
    避免重启清零让调用方"满血复活"。精度损失 ≤ 1 分钟。
    """

    __tablename__ = "tb_integration_quota_day"
    __table_args__ = (
        PrimaryKeyConstraint("integration_id", "day", name="pk_tb_integration_quota_day"),
    )

    integration_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    day: Mapped[str] = mapped_column(String(8), nullable=False)
    day_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TbApiAccessLog(Base):
    """对外网关 /open/v1/* 调用日志。

    每次调用落一行,无论成功、鉴权拒绝、限流拒绝还是上游错误。鉴权失败发生在
    解析集成之前时,integration_id/key_id/app_* 列可能为空。
    """

    __tablename__ = "tb_api_access_log"
    __table_args__ = (Index("idx_tb_api_access_log_intg", "integration_id", "create_time"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    integration_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    key_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    app_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    app_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TbAlertRule(Base):
    """可观测性告警规则。

    评估器(AlertEvaluator)周期扫描 enabled=1 的规则,把 metric_type 翻译成对
    tb_app_log 的聚合查询;命中阈值且不在冷却期则写入 tb_alert_record。
    详见 docs/observability-alert-design.md。
    """

    __tablename__ = "tb_alert_rule"
    __table_args__ = (Index("idx_tb_alert_rule_enabled", "enabled"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 监控指标: success_rate / p95_latency / error_rate / token_usage_daily
    #          / request_latency / consecutive_failures / negative_feedback_rate
    #          / llm_error_count_by_type
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 仅 metric_type=llm_error_count_by_type 时有意义;空=任意 LLM 错误
    target_error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 比较运算符: lt / lte / gt / gte / eq
    operator: Mapped[str] = mapped_column(String(8), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    # 阈值单位: % / ms / tokens
    threshold_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 监控范围: global / per_app / per_request
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    # 触发后产生的告警级别: critical / warning / info
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    # 通知渠道 JSON 数组字符串, 例如 ["inbox"]
    notify_channels: Mapped[str] = mapped_column(Text, nullable=False)
    message_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    # 运行时统计
    trigger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_triggered_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbAlertRecord(Base):
    """告警触发记录。评估器命中阈值时写入,「告警中心」页消费。

    rule_name 为触发时的快照,即使规则被删除,历史告警仍可正常展示。
    """

    __tablename__ = "tb_alert_record"
    __table_args__ = (Index("idx_tb_alert_record_status", "status", "triggered_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    # 状态: firing / resolved / acknowledged
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    # scope=per_app 时填具体应用,global 时为空
    app_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    app_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resolved_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    acknowledged_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TbAppMetricMinute(Base):
    """应用调用指标的分钟级预聚合。

    由 MetricRollupWorker 周期性从 tb_app_log 聚合而来,服务可观测性面板与
    告警溯源曲线。派生缓存,可随时按 tb_app_log 重建。列风格对齐
    tb_integration_quota_day(自然复合主键、精简列、仅 update_time)。
    详见 docs/observability-metrics-rollup-design.md。
    """

    __tablename__ = "tb_app_metric_minute"
    __table_args__ = (
        PrimaryKeyConstraint("bucket_start", "app_id", name="pk_tb_app_metric_minute"),
    )

    # 分钟桶起点, Unix ms, 对齐到整分钟 (create_time // 60000 * 60000)
    bucket_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 应用 ID; 0 = 无归属应用(如直连模型网关的调用)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # latency_ms 非空的样本数(avg 分母 / 直方图样本总数)
    latency_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_sum: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 各延迟区间的计数, JSON int 数组, 见 metric_rollup_service._LATENCY_BUCKETS_MS
    latency_histogram: Mapped[str] = mapped_column(Text, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
