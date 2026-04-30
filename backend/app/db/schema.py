from sqlalchemy import BigInteger, Integer, String, Text, UniqueConstraint
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


class TbSkill(Base):
    __tablename__ = "tb_skill"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
