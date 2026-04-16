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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
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
