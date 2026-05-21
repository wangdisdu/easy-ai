class ErrorCode:
    INTERNAL_ERROR = 1000
    BAD_REQUEST = 1001
    UNAUTHORIZED = 1002
    FORBIDDEN = 1003
    DATA_NOT_FOUND = 1004
    VALIDATION_FAILED = 1005
    DATA_DUPLICATE = 1006

    # 上游 RAGFlow 相关(详见 docs/knowledge-rag-integration-design.md §9)
    # 拆出独立编码方便日志聚合与前端针对性弹窗;字段级别错误(如 KB 不存在、
    # 重名)仍复用通用码 + descriptive msg,与 app_service 模式一致。
    UPSTREAM_RAGFLOW_ERROR = 1200
    UPSTREAM_AUTH_FAILED = 1201
    KB_RAGFLOW_DATASET_MISSING = 1202
    KB_EMBEDDING_MISMATCH = 1203
    # 创建 KB 时未指定 embedding,且系统设置里也没有默认 embedding
    KB_EMBEDDING_NOT_CONFIGURED = 1204

    # 应用集成管理 API(对外网关错误走 IntegrationApiError,不在此处)
    # 详见 docs/application-integration-design.md §12.1
    INTEGRATION_NOT_FOUND = 1300
    INTEGRATION_NAME_DUPLICATE = 1301
    # 绑定了 P1 未支持的应用类型(agent_flow / kb_push)
    INTEGRATION_BIND_NOT_ALLOWED = 1302
    # 客户端尝试获取已不可见的 API Key 明文
    API_KEY_PLAINTEXT_INVISIBLE = 1303
