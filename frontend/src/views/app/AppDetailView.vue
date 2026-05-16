<template>
  <div v-if="app" class="detail-page">
    <a-button type="link" class="back-btn" @click="router.push('/app')">
      <template #icon><ArrowLeftOutlined /></template>
      返回应用列表
    </a-button>

    <a-alert
      v-if="app.app_status === 'draft'"
      message="该应用当前处于草稿状态，仅可在平台内编辑和测试，尚未对外开放。"
      type="warning"
      show-icon
      banner
      class="draft-banner"
    >
      <template #action>
        <a-button v-if="canPublish" type="primary" size="small" @click="openPublish">发布应用</a-button>
      </template>
    </a-alert>

    <section class="hero-card">
      <div class="hero-main">
        <div class="hero-top">
          <div :class="['hero-icon', `app-type--${app.app_type}`]">
            {{ typeEmoji[app.app_type] || "💬" }}
          </div>
          <div class="hero-title-wrap">
            <div class="hero-badges">
              <span :class="['app-type-tag', `app-type--${app.app_type}`]">
                {{ appTypeLabel[app.app_type] || app.app_type }}
              </span>
              <span :class="['status-badge', `status--${app.app_status}`]">
                <span class="status-dot" />
                {{ statusLabel[app.app_status] || app.app_status }}
              </span>
            </div>
            <h2 class="hero-title">{{ app.name }}</h2>
            <p class="hero-desc">{{ app.description || "暂无描述" }}</p>
            <div v-if="app.categories && app.categories.length" class="hero-cat-tags">
              <a-tag v-for="c in app.categories" :key="c.id" color="blue">
                {{ c.name }}
              </a-tag>
            </div>
          </div>
        </div>

        <div v-if="app.app_type === 'agent_flow'" class="hero-metrics">
          <div class="metric-card">
            <span class="metric-label">访问范围</span>
            <span class="metric-value metric-value--small">
              {{ accessScopeLabel[app.access_scope || ""] || app.access_scope || "-" }}
            </span>
          </div>
          <div class="metric-card">
            <span class="metric-label">限流</span>
            <span class="metric-value metric-value--small">{{ app.rate_limit ?? "-" }} 次/分</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">调用日志</span>
            <span class="metric-value metric-value--small">{{ app.enable_log ? "已启用" : "未启用" }}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">版本</span>
            <span class="metric-value metric-value--small">{{ app.current_version || "未发布" }}</span>
          </div>
        </div>
        <div v-else class="hero-metrics">
          <div class="metric-card">
            <span class="metric-label">访问范围</span>
            <span class="metric-value metric-value--small">
              {{ accessScopeLabel[app.access_scope || ""] || app.access_scope || "-" }}
            </span>
          </div>
          <div class="metric-card">
            <span class="metric-label">模型参数</span>
            <span class="metric-value metric-value--small">{{ Object.keys(app.model_setting || {}).length }} 项</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">模型</span>
            <span class="metric-value metric-value--small">{{ app.model || "-" }}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">版本</span>
            <span class="metric-value metric-value--small">{{ app.current_version || "未发布" }}</span>
          </div>
        </div>
      </div>

      <div class="hero-actions">
        <a-button v-if="canEdit" @click="router.push(`/app/${app.id}/edit`)">编辑</a-button>
        <a-button
          v-if="app.app_type === 'agent_flow'"
          type="primary"
          :disabled="!app.flowise_chatflow_id"
          :title="app.flowise_chatflow_id ? '' : '未关联 Flowise 画布'"
          @click="openFlowiseCanvas"
        >
          打开画布
        </a-button>
        <a-button v-if="['llm', 'agent', 'rag'].includes(app.app_type)" @click="openTestDrawer">测试</a-button>
        <a-button v-if="canPublish && app.app_status === 'published'" @click="onOffline">下线</a-button>
        <a-button v-if="canPublish && app.app_status === 'offline'" type="primary" @click="openPublish">上线</a-button>
        <a-button v-if="canPublish && app.app_status === 'draft'" type="primary" @click="openPublish">发布应用</a-button>
        <a-button v-if="canPublish && app.app_status === 'published'" type="primary" @click="openPublish">发布新版本</a-button>
        <a-popconfirm v-if="canEdit" title="确定删除该应用？" @confirm="onDelete">
          <a-button danger>删除</a-button>
        </a-popconfirm>
      </div>
    </section>

    <a-tabs v-model:activeKey="activeTab" class="detail-tabs">
      <a-tab-pane key="config" tab="应用配置">
        <!-- agent_flow 专属布局：不展示模型/Temperature/Max Tokens 等无关字段，强调画布关联 -->
        <template v-if="app.app_type === 'agent_flow'">
          <section class="panel-card panel-card--full">
            <div class="panel-head">
              <div>
                <h3 class="panel-title">基础信息</h3>
                <p class="panel-sub">应用基本属性与平台接入策略。</p>
              </div>
            </div>
            <div class="kv-grid">
              <div class="kv-item">
                <span class="kv-label">应用类型</span>
                <span class="kv-value">{{ appTypeLabel[app.app_type] || app.app_type }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">访问范围</span>
                <span class="kv-value">{{ accessScopeLabel[app.access_scope || ""] || app.access_scope || "-" }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">限流</span>
                <span class="kv-value">{{ app.rate_limit ?? "-" }} 次/分</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">调用日志</span>
                <span class="kv-value">{{ app.enable_log ? "已启用" : "未启用" }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">创建时间</span>
                <span class="kv-value">{{ formatMs(app.create_time) }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">最近更新</span>
                <span class="kv-value">{{ formatMs(app.update_time) }}</span>
              </div>
            </div>
            <div v-if="app.description" class="agent-flow-desc">
              <div class="agent-flow-desc-label">应用描述</div>
              <div class="agent-flow-desc-text">{{ app.description }}</div>
            </div>
          </section>

          <section class="panel-card panel-card--full">
            <div class="panel-head">
              <div>
                <h3 class="panel-title">版本历史</h3>
                <p class="panel-sub">应用发布记录与版本说明。</p>
              </div>
            </div>
            <div v-if="versions.length" class="version-list">
              <div v-for="version in versions" :key="version.id" class="version-item">
                <div>
                  <div class="version-name">{{ version.version }}</div>
                  <div class="version-note">{{ version.version_note || "无版本说明" }}</div>
                </div>
                <span class="version-time">{{ formatMs(version.published_time) }}</span>
              </div>
            </div>
            <a-empty v-else :image="false" description="暂无版本记录" />
          </section>
        </template>

        <!-- 其它应用类型保持原有布局 -->
        <template v-else>
        <div class="overview-grid">
          <section class="panel-card">
            <div class="panel-head">
              <div>
                <h3 class="panel-title">基础配置</h3>
                <p class="panel-sub">应用基本属性、模型参数和平台接入配置。</p>
              </div>
            </div>
            <div class="kv-grid">
              <div class="kv-item">
                <span class="kv-label">应用类型</span>
                <span class="kv-value">{{ appTypeLabel[app.app_type] || app.app_type }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">访问范围</span>
                <span class="kv-value">{{ accessScopeLabel[app.access_scope || ""] || app.access_scope || "-" }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">供应商</span>
                <span class="kv-value">{{ providerName || "-" }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">模型</span>
                <span class="kv-value">{{ app.model || "-" }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">Temperature</span>
                <span class="kv-value">{{ app.model_setting?.temperature ?? "-" }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">Max Tokens</span>
                <span class="kv-value">{{ app.model_setting?.max_tokens ?? "-" }}</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">限流</span>
                <span class="kv-value">{{ app.rate_limit ?? "-" }} 次/分</span>
              </div>
              <div class="kv-item">
                <span class="kv-label">调用日志</span>
                <span class="kv-value">{{ app.enable_log ? "已启用" : "未启用" }}</span>
              </div>
            </div>
          </section>

          <section class="panel-card">
            <div class="panel-head">
              <div>
                <h3 class="panel-title">类型配置摘要</h3>
                <p class="panel-sub">{{ typeConfigTitle[app.app_type] || "当前应用的专属配置摘要。" }}</p>
              </div>
            </div>
            <div v-if="summaryRows.length" class="kv-grid">
              <div v-for="row in summaryRows" :key="row.label" class="kv-item">
                <span class="kv-label">{{ row.label }}</span>
                <span class="kv-value">{{ row.value }}</span>
              </div>
            </div>
            <div v-else class="empty-note">当前类型暂无额外配置</div>
          </section>
        </div>

        <section class="panel-card panel-card--full">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">版本历史</h3>
              <p class="panel-sub">应用发布记录与版本说明。</p>
            </div>
          </div>
          <div v-if="versions.length" class="version-list">
            <div v-for="version in versions" :key="version.id" class="version-item">
              <div>
                <div class="version-name">{{ version.version }}</div>
                <div class="version-note">{{ version.version_note || "无版本说明" }}</div>
              </div>
              <span class="version-time">{{ formatMs(version.published_time) }}</span>
            </div>
          </div>
          <a-empty v-else :image="false" description="暂无版本记录" />
        </section>
        </template>
      </a-tab-pane>

      <a-tab-pane key="history" tab="历史消息">
        <section class="panel-card panel-card--full">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">历史消息</h3>
              <p class="panel-sub">展示应用最近的运行与测试日志。</p>
            </div>
          </div>

          <div v-if="appLogs.length" class="log-list">
            <div
              v-for="log in appLogs"
              :key="log.id"
              class="log-row"
              @click="openLogDetail(log)"
            >
              <div class="log-row-main">
                <div class="log-meta">
                  <span :class="['log-type', `log-type--${log.request_type}`]">
                    {{ requestTypeLabel[log.request_type] || log.request_type }}
                  </span>
                  <span :class="['log-status', log.success ? 'log-status--success' : 'log-status--error']">
                    {{ log.success ? "成功" : "失败" }}
                  </span>
                  <span class="log-time">{{ formatMs(log.create_time) }}</span>
                </div>
                <div class="log-preview">{{ logPreview(log) }}</div>
              </div>
              <div class="log-side">
                <span>{{ log.model || "-" }}</span>
                <span>{{ log.latency_ms ?? "-" }} ms</span>
                <RightOutlined class="log-arrow" />
              </div>
            </div>
          </div>
          <a-empty v-else :image="false" description="暂无历史消息" />
        </section>
      </a-tab-pane>

      <a-tab-pane v-if="showMemoryTab" key="memory" tab="记忆管理">
        <section class="panel-card panel-card--full">
          <AppMemoryPanel :app-id="app.id" :app-name="app.name" />
        </section>
      </a-tab-pane>

      <a-tab-pane v-if="showApiDocsTab" key="api-docs" tab="API 及文档">
        <section class="panel-card panel-card--full">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">接入地址</h3>
              <p class="panel-sub">标准 HTTP 接入方式，正式访问前需在应用集成中创建 API Key。</p>
            </div>
          </div>
          <div class="endpoint-box">
            <span class="endpoint-method">POST</span>
            <code>{{ apiEndpoint }}</code>
          </div>
          <div class="doc-block">
            <div class="doc-title">认证方式</div>
            <div class="endpoint-box endpoint-box--soft">
              <code>Authorization: Bearer {"{YOUR_API_KEY}"}</code>
            </div>
          </div>
          <div class="doc-block">
            <div class="doc-title">请求示例</div>
            <pre class="prompt-block">{{ requestExample }}</pre>
          </div>
          <div class="doc-block">
            <div class="doc-title">响应示例</div>
            <pre class="prompt-block">{{ responseExample }}</pre>
          </div>
        </section>
      </a-tab-pane>
    </a-tabs>

    <a-modal
      v-model:open="publishOpen"
      title="发布应用"
      :confirm-loading="publishing"
      destroy-on-close
      @ok="doPublish"
    >
      <a-form layout="vertical">
        <a-form-item label="版本号" required>
          <a-input v-model:value="publishForm.version" placeholder="如 v1.0.0" />
        </a-form-item>
        <a-form-item label="版本说明">
          <a-textarea v-model:value="publishForm.version_note" :rows="3" placeholder="本次发布的变更说明" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-drawer
      v-model:open="testOpen"
      title="应用测试"
      width="560"
      destroy-on-close
      :body-style="{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }"
    >
      <template v-if="['llm', 'agent', 'rag'].includes(app?.app_type ?? '')">
        <div class="test-chat-body" @click="onTestPanelClick">
          <!-- 输入 + 操作合并区 -->
          <div class="test-composer">
            <!-- LLM 输入表单 -->
            <template v-if="app?.app_type === 'llm'">
              <a-form v-if="llmInputVars.length" layout="vertical" class="test-composer-form">
                <a-form-item
                  v-for="item in llmInputVars"
                  :key="item.name || item.label"
                  :label="item.label || item.name || '测试输入'"
                  class="test-form-item"
                >
                  <a-input-number
                    v-if="item.type === 'number'"
                    v-model:value="llmTestInputs[item.name]"
                    class="full-width"
                    placeholder="请输入测试内容"
                  />
                  <a-textarea
                    v-else-if="item.type === 'textarea'"
                    v-model:value="llmTestInputs[item.name]"
                    :rows="3"
                    :auto-size="{ minRows: 2, maxRows: 6 }"
                    placeholder="请输入测试内容"
                  />
                  <a-input
                    v-else
                    v-model:value="llmTestInputs[item.name]"
                    :placeholder="`请输入${item.label || item.name || '测试内容'}`"
                  />
                </a-form-item>
              </a-form>
              <div v-else class="test-composer-hint">未定义输入变量，将直接按当前 Prompt 试跑</div>
            </template>

            <!-- Agent 输入 -->
            <template v-if="app?.app_type === 'agent'">
              <a-textarea
                v-model:value="agentTestMessage"
                :auto-size="{ minRows: 2, maxRows: 6 }"
                placeholder="输入消息，Enter 发送，Shift+Enter 换行"
                :disabled="isStreaming"
                class="test-composer-textarea"
                @pressEnter="(e: KeyboardEvent) => { if (!e.shiftKey) { e.preventDefault(); onTestAgent(); } }"
              />
            </template>

            <!-- RAG 输入 -->
            <template v-if="app?.app_type === 'rag'">
              <a-textarea
                v-model:value="ragTestQuery"
                :auto-size="{ minRows: 2, maxRows: 6 }"
                placeholder="输入问题，回车提交"
                :disabled="isStreaming"
                class="test-composer-textarea"
                @pressEnter="(e: KeyboardEvent) => { if (!e.shiftKey) { e.preventDefault(); onTestRag(); } }"
              />
            </template>

            <!-- 底部操作条 -->
            <div class="test-composer-bar">
              <span v-if="streamMeta.model" class="test-meta-tag">{{ streamMeta.model }}</span>
              <span class="test-composer-spacer" />
              <a-button v-if="isStreaming" size="small" danger @click="onStopStream">停止</a-button>
              <a-button
                type="primary"
                size="small"
                :loading="isStreaming"
                :disabled="isStreaming"
                @click="dispatchTestRun"
              >
                运行
              </a-button>
            </div>
          </div>

          <!-- 消息时间轴 -->
          <div v-if="hasTestOutput" class="test-timeline">
            <!-- 用户消息 -->
            <div v-if="userMessageText" class="tl-item">
              <div class="tl-rail">
                <span class="tl-dot tl-dot--human" />
                <span class="tl-line" />
              </div>
              <div class="tl-body">
                <div class="msg-card msg-card--human">
                  <div class="msg-header">
                    <span class="msg-type-badge msg-type-badge--human">{{ msgTypeLabel.human }}</span>
                  </div>
                  <div class="msg-content">{{ userMessageText }}</div>
                </div>
              </div>
            </div>

            <!-- 工具调用消息 -->
            <div
              v-for="(tc, idx) in streamingToolCalls"
              :key="'tc-' + idx"
              class="tl-item"
            >
              <div class="tl-rail">
                <span class="tl-dot tl-dot--tool" />
                <span class="tl-line" />
              </div>
              <div class="tl-body">
                <div class="msg-card msg-card--tool">
                  <div class="msg-header">
                    <span class="msg-type-badge msg-type-badge--tool">{{ isSubagentTask(tc.name, tc.arguments) ? "子代理" : msgTypeLabel.tool }}</span>
                    <span class="msg-tool-status">
                      <a-spin v-if="tc.status === 'running' || tc.status === 'subagent_hitl'" size="small" />
                      <span v-else class="msg-tool-status-done">{{ tc.status === "error" ? "error" : "done" }}</span>
                    </span>
                  </div>
                  <div class="msg-tool-calls">
                    <div class="msg-tool-call">
                      <span class="msg-tool-name">{{ toolDisplayIcon(tc.name, tc.arguments) }} {{ toolDisplayName(tc.name, tc.arguments) }}</span>
                      <pre v-if="tc.arguments && Object.keys(tc.arguments).length" class="msg-tool-args">{{ stringifyJson(tc.arguments) }}</pre>
                    </div>
                  </div>
                  <div v-if="tc.result" class="msg-content msg-content--tool-result">{{ truncateToolResult(tc.result, 500) }}</div>
                </div>
              </div>
            </div>

            <!-- HITL 确认卡片 -->
            <div v-if="pendingHitl" class="tl-item">
              <div class="tl-rail">
                <span class="tl-dot tl-dot--hitl" />
                <span class="tl-line" />
              </div>
              <div class="tl-body">
                <HitlConfirmCard
                  :payload="pendingHitl"
                  :busy="hitlBusy"
                  @respond="onHitlRespond"
                  @timeout="hitlTimeoutFlag = true"
                />
              </div>
            </div>

            <!-- AI 回复消息 -->
            <div v-if="streamingContent || isStreaming" class="tl-item">
              <div class="tl-rail">
                <span class="tl-dot tl-dot--ai" />
                <span class="tl-line tl-line--last" />
              </div>
              <div class="tl-body">
                <div class="msg-card msg-card--ai">
                  <div class="msg-header">
                    <span class="msg-type-badge msg-type-badge--ai">{{ msgTypeLabel.ai }}</span>
                    <span v-if="streamMeta.tokenUsage?.total_tokens" class="msg-tokens">
                      {{ streamMeta.tokenUsage.total_tokens }} tokens
                      (入 {{ streamMeta.tokenUsage.input_tokens ?? "-" }} / 出 {{ streamMeta.tokenUsage.output_tokens ?? "-" }})
                    </span>
                  </div>
                  <div
                    v-if="streamingContent"
                    class="msg-content"
                    v-html="renderMarkdown(streamingContent + (isStreaming ? '▍' : ''))"
                  ></div>
                  <div v-else class="msg-content msg-content--empty">
                    <a-spin size="small" /> 正在思考...
                  </div>
                </div>

                <!-- RAG references 卡片列表 -->
                <div v-if="ragReferences.length" class="rag-refs">
                  <div class="rag-refs-head">参考文档({{ ragReferences.length }})</div>
                  <div class="rag-refs-list">
                    <div
                      v-for="(ref, i) in ragReferences"
                      :key="ref.chunk_id || i"
                      class="rag-ref-card"
                      @click="openRefPreview(ref)"
                    >
                      <div class="rag-ref-head">
                        <span class="rag-ref-name">{{ ref.doc_name || "(未命名)" }}</span>
                        <span v-if="ref.similarity != null" class="rag-ref-sim">
                          相似度 {{ (ref.similarity * 100).toFixed(1) }}%
                        </span>
                      </div>
                      <div class="rag-ref-snippet">{{ ref.snippet }}</div>
                      <div v-if="ref.doc_ref" class="rag-ref-foot">
                        <span class="rag-ref-code">[[doc:{{ ref.doc_ref }}]]</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 统计信息 -->
            <div v-if="!isStreaming && streamMeta.latency_ms" class="tl-item tl-item--stats">
              <div class="tl-rail">
                <span class="tl-dot tl-dot--done" />
              </div>
              <div class="tl-body">
                <div class="test-stats">
                  <span>耗时 {{ streamMeta.latency_ms }} ms</span>
                  <span v-if="streamMeta.tokenUsage?.total_tokens">
                    总计 {{ streamMeta.tokenUsage.total_tokens }} tokens
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-else class="test-empty">
            <div class="test-empty-icon">
              {{ app?.app_type === 'agent' ? '🤖' : app?.app_type === 'rag' ? '📚' : '✨' }}
            </div>
            <div class="test-empty-text">
              {{
                app?.app_type === 'agent'
                  ? '输入消息开始与 Agent 对话'
                  : app?.app_type === 'rag'
                    ? '输入问题,从绑定的知识库检索 + 生成答案'
                    : '填写输入变量后点击运行'
              }}
            </div>
          </div>
        </div>
      </template>
      <div v-else class="test-chat-body">
        <a-empty :image="false" description="当前应用类型暂未接入测试面板" style="margin: auto" />
      </div>
    </a-drawer>

    <a-drawer
      v-model:open="logDetailOpen"
      title="消息详情"
      width="720"
      destroy-on-close
    >
      <template #extra>
        <a-segmented v-model:value="logViewMode" :options="[{ label: '格式化', value: 'formatted' }, { label: '原始格式', value: 'raw' }]" size="small" />
      </template>

      <div v-if="currentLog" class="log-detail">
        <!-- 原始格式 -->
        <template v-if="logViewMode === 'raw'">
          <div class="config-block">
            <div class="config-label">请求</div>
            <pre class="prompt-block">{{ stringifyJson(currentLog.request_payload ?? {}) }}</pre>
          </div>
          <div class="config-block">
            <div class="config-label">响应</div>
            <pre class="prompt-block">{{ stringifyJson(currentLog.response_payload ?? {}) }}</pre>
          </div>
        </template>

        <!-- 格式化展示 -->
        <template v-else>
          <!-- 概览 -->
          <div class="log-overview">
            <div class="log-overview-row">
              <span class="log-overview-label">Trace ID</span>
              <span class="log-overview-value log-overview-mono">{{ currentLog.langfuse_trace_id || "-" }}</span>
            </div>
            <div class="log-overview-row">
              <span class="log-overview-label">时间</span>
              <span class="log-overview-value">{{ formatMs(currentLog.create_time) }}</span>
            </div>
            <div class="log-overview-row">
              <span class="log-overview-label">状态</span>
              <span :class="['log-status', currentLog.success ? 'log-status--success' : 'log-status--error']">
                {{ currentLog.success ? "成功" : "失败" }}
              </span>
            </div>
            <div class="log-overview-row">
              <span class="log-overview-label">模型</span>
              <span class="log-overview-value">{{ currentLog.model || "-" }}</span>
            </div>
            <div class="log-overview-row">
              <span class="log-overview-label">耗时</span>
              <span class="log-overview-value">{{ currentLog.latency_ms ?? "-" }} ms</span>
            </div>
            <div class="log-overview-row">
              <span class="log-overview-label">Token 用量</span>
              <span class="log-overview-value">
                总计 {{ currentLog.total_tokens ?? "-" }} (输入 {{ currentLog.input_tokens ?? "-" }} / 输出 {{ currentLog.output_tokens ?? "-" }})
              </span>
            </div>
          </div>

          <div v-if="currentLog.error_message" class="log-error">{{ currentLog.error_message }}</div>

          <!-- 消息时间轴 -->
          <div class="log-timeline">
            <div v-for="(msg, idx) in parsedMessages" :key="idx" class="tl-item">
              <div class="tl-rail">
                <span :class="['tl-dot', `tl-dot--${msg.type}`]" />
                <span v-if="idx < parsedMessages.length - 1" class="tl-line" />
              </div>
              <div class="tl-body">
                <div :class="['msg-card', `msg-card--${msg.type}`]">
                  <div class="msg-header">
                    <span :class="['msg-type-badge', `msg-type-badge--${msg.type}`]">{{ msgTypeLabel[msg.type] || msg.type }}</span>
                    <span v-if="msg.tokens.total !== null" class="msg-tokens">
                      {{ msg.tokens.total }} tokens (入 {{ msg.tokens.input ?? "-" }} / 出 {{ msg.tokens.output ?? "-" }})
                    </span>
                  </div>
                  <div v-if="msg.toolCalls && msg.toolCalls.length" class="msg-tool-calls">
                    <div v-for="(tc, ti) in msg.toolCalls" :key="ti" class="msg-tool-call">
                      <span class="msg-tool-name">{{ toolDisplayIcon(tc.name, tc.args) }} {{ toolDisplayName(tc.name, tc.args) }}</span>
                      <pre class="msg-tool-args">{{ stringifyJson(tc.args) }}</pre>
                    </div>
                  </div>
                  <div v-if="msg.content" class="msg-content" v-html="renderMarkdown(msg.content)"></div>
                  <div v-else-if="!msg.toolCalls?.length" class="msg-content msg-content--empty">（无文本内容）</div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined, RightOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { renderMarkdownWithDocRefs } from "@/composables/useMarkdown";
import * as appApi from "@/api/app";
import * as kbApi from "@/api/kb";
import * as llmApi from "@/api/llm";
import type { HitlAction } from "@/api/conversation";
import type { AppLogResp, AppResp, AppRunReference, AppVersionResp } from "@/api/types";
import type { SSEEvent } from "@/api/sse";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";
import { formatMs } from "@/utils/time";
import AppMemoryPanel from "@/components/AppMemoryPanel.vue";
import HitlConfirmCard, { type HitlPayload } from "@/components/HitlConfirmCard.vue";

const route = useRoute();
const router = useRouter();

const app = ref<AppResp | null>(null);
const versions = ref<AppVersionResp[]>([]);
const appLogs = ref<AppLogResp[]>([]);
const providers = ref<Array<{ id: string; name: string }>>([]);
const activeTab = ref("config");
const publishOpen = ref(false);
const publishing = ref(false);
const testOpen = ref(false);
const agentTestMessage = ref("");
const llmTestInputs = reactive<Record<string, string | number | undefined>>({});
const ragTestQuery = ref("");
const ragReferences = ref<AppRunReference[]>([]);
const logDetailOpen = ref(false);
const currentLog = ref<AppLogResp | null>(null);
const logViewMode = ref<"formatted" | "raw">("formatted");
const publishForm = reactive({ version: "", version_note: "" });

// 流式输出状态
interface StreamingToolCall {
  tool_call_id: string;
  name: string;
  status: "running" | "done" | "error" | "subagent_hitl";
  arguments?: Record<string, unknown>;
  result?: string;
}
interface TokenUsage {
  total_tokens: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
}
const isStreaming = ref(false);
const streamingContent = ref("");
const streamingToolCalls = ref<StreamingToolCall[]>([]);
// 文本块 id 集合（`${message_id}:${block_index}`）：仅文本块 delta 计入正文。
let streamTextBlocks = new Set<string>();
const streamAbort = ref<{ abort: () => void } | null>(null);
const userMessageText = ref("");
const pendingHitl = ref<HitlPayload | null>(null);
// 被中断 run 的 run_id（从 hitl.required 信封捕获），续跑回传作 parent_run_id
const pendingHitlRunId = ref<string | null>(null);
const hitlBusy = ref(false);
const currentThreadId = ref<string | null>(null);
let hitlTimeoutFlag = false;
const streamMeta = reactive<{ model: string; latency_ms: number | null; tokenUsage: TokenUsage | null }>({
  model: "",
  latency_ms: null,
  tokenUsage: null,
});

const hasTestOutput = computed(() => isStreaming.value || streamingContent.value || streamingToolCalls.value.length || userMessageText.value);

const msgTypeLabel: Record<string, string> = {
  human: "用户",
  ai: "AI",
  tool: "工具",
  system: "系统",
};

// ── 工具展示工具函数（共享 composable） ──
import {
  isSubagentTask,
  toolDisplayName,
  toolDisplayIcon,
} from "@/composables/useToolDisplay";

interface ParsedMessage {
  type: string;
  content: string;
  toolCalls?: Array<{ name: string; args: Record<string, unknown> }>;
  tokens: { total: number | null; input: number | null; output: number | null };
}

const parsedMessages = computed<ParsedMessage[]>(() => {
  const resp = currentLog.value?.response_payload as Record<string, unknown> | null;
  if (!resp) return [];
  const result = resp.result as Record<string, unknown> | undefined;
  if (!result) return [];
  const messages = result.messages as Array<Record<string, unknown>> | undefined;
  if (!Array.isArray(messages)) return [];

  return messages.map((msg) => {
    const usage = msg.usage_metadata as Record<string, number> | undefined;
    const toolCalls = msg.tool_calls as Array<{ name: string; args: Record<string, unknown> }> | undefined;
    return {
      type: (msg.type as string) || "unknown",
      content: typeof msg.content === "string" ? msg.content : "",
      toolCalls: toolCalls?.length ? toolCalls : undefined,
      tokens: {
        total: usage?.total_tokens ?? null,
        input: usage?.input_tokens ?? null,
        output: usage?.output_tokens ?? null,
      },
    };
  });
});

// ragReferences 由 SSE references 事件填充, 这里反推成 ref → 文档名
// 映射,供 [[doc:xxx]] 内联链接渲染时显示文档名
const ragRefNames = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const r of ragReferences.value) {
    if (r.doc_ref && r.doc_name && !map[r.doc_ref]) {
      map[r.doc_ref] = r.doc_name;
    }
  }
  return map;
});

function renderMarkdown(text: string): string {
  return renderMarkdownWithDocRefs(text, ragRefNames.value);
}

// 事件委托:点 .doc-ref-link 时反查 ref → 新页签跳预览
async function onTestPanelClick(ev: MouseEvent) {
  const target = (ev.target as HTMLElement | null)?.closest?.(".doc-ref-link") as
    | HTMLAnchorElement
    | null;
  if (!target) return;
  ev.preventDefault();
  const ref = target.dataset.docRef;
  if (!ref) return;
  try {
    const { data } = await kbApi.getKbDocumentByRef(ref);
    const doc = data.data;
    const url = router.resolve({
      name: "knowledge-doc-preview",
      params: { kbId: doc.kb_id, docId: doc.id },
    }).href;
    window.open(url, "_blank");
  } catch (e) {
    message.error("找不到引用文档: " + ((e as Error).message || ref));
  }
}

const appTypeLabel: Record<string, string> = {
  llm: "LLM 应用",
  rag: "RAG 应用",
  nl2sql: "NL2SQL 应用",
  agent: "Agent 智能体",
  agent_flow: "Agent Flow 编排",
};

const statusLabel: Record<string, string> = {
  draft: "草稿",
  published: "已发布",
  offline: "已下线",
};

const accessScopeLabel: Record<string, string> = {
  internal: "企业内部",
  api: "API 开放",
  embed: "嵌入式",
};

const typeEmoji: Record<string, string> = {
  rag: "📚",
  llm: "✨",
  nl2sql: "🗄",
  agent: "🤖",
  agent_flow: "🔄",
};

const requestTypeLabel: Record<string, string> = {
  test: "平台测试",
  chat: "平台对话",
  api: "API 调用",
};

const typeConfigTitle: Record<string, string> = {
  rag: "知识库、检索、Rerank 与总结配置。",
  llm: "输入变量、提示词模板与输出配置。",
  nl2sql: "数据库连接与 Schema 描述。",
  agent: "工具、技能、行为参数与子智能体配置。",
  agent_flow: "Agent Flow 画布在 Flowise 中编辑，点击「打开画布」进入。",
};

const showApiDocsTab = computed(() => app.value?.app_status === "published");

const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.APP_EDIT));
const canPublish = computed(() => auth.hasPermission(PERM.APP_PUBLISH));
const showMemoryTab = computed(() => {
  const me = auth.user?.id;
  if (!me || !app.value?.create_user) return false;
  return String(app.value.create_user) === String(me);
});
const llmInputVars = computed<Array<{ name: string; label?: string; type?: string }>>(() => {
  const inputVars = app.value?.app_config?.input_vars;
  return Array.isArray(inputVars) ? (inputVars as Array<{ name: string; label?: string; type?: string }>) : [];
});

const providerName = computed(() => {
  if (!app.value?.provider_id) return "";
  return providers.value.find((item) => item.id === app.value?.provider_id)?.name || "";
});

const summaryRows = computed(() => {
  const config = app.value?.app_config || {};
  if (!app.value) return [];
  if (app.value.app_type === "llm") {
    return [
      { label: "输入变量数", value: String(((config.input_vars as unknown[]) || []).length) },
      { label: "输出格式", value: String(config.output_format || "text") },
      { label: "输出变量数", value: String(((config.output_vars as unknown[]) || []).length) },
    ];
  }
  if (app.value.app_type === "rag") {
    return [
      { label: "知识库", value: ((config.kb_ids as string[]) || []).join(", ") || "-" },
      { label: "相似度阈值", value: String(config.similarity_threshold ?? "-") },
      { label: "Top N", value: String(config.top_n ?? "-") },
      { label: "Rerank", value: config.enable_rerank ? "已启用" : "未启用" },
    ];
  }
  if (app.value.app_type === "nl2sql") {
    return [
      { label: "数据库连接", value: String(config.db_connection || "-") },
      { label: "Schema", value: String(config.db_schema || "-") },
    ];
  }
  if (app.value.app_type === "agent") {
    return [
      { label: "工具数", value: String((app.value.tool_ids ?? []).length) },
      { label: "技能数", value: String((app.value.skill_ids ?? []).length) },
      { label: "最大轮次", value: String(config.max_turns ?? "-") },
      { label: "自动执行", value: config.allow_auto_exec ? "允许" : "需确认" },
    ];
  }
  // agent_flow 的画布与配置完全在 Flowise 维护,easy-ai 详情页不展示编排元数据
  return [];
});

const apiEndpoint = computed(() => {
  if (!app.value) return "";
  return `${window.location.origin}/api/v1/open/app/${app.value.id}`;
});

const requestExample = computed(() => {
  if (!app.value) return "";
  const config = app.value.app_config || {};
  if (app.value.app_type === "llm") {
    const inputs = Object.fromEntries(
      (((config.input_vars as Array<{ name?: string }>) || []).map((item) => [
        item.name || "input",
        `示例${item.name || "值"}`,
      ])) || []
    );
    return stringifyJson({
      inputs,
      session_id: "sess-demo-001",
    });
  }
  return stringifyJson({
    query: "示例请求内容",
    session_id: "sess-demo-001",
  });
});

const responseExample = computed(() =>
  stringifyJson({
    code: 0,
    msg: "ok",
    data: app.value?.app_type === "llm" ? { result: "示例输出" } : { answer: "示例响应" },
    session_id: "sess-demo-001",
    usage: { prompt_tokens: 120, completion_tokens: 280 },
  })
);

function stringifyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function extractText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    // OpenAI 多模态 content：[{ type: 'text', text: '...' }, ...]
    return value
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const it = item as Record<string, unknown>;
          if (typeof it.text === "string") return it.text;
          if (typeof it.content === "string") return it.content;
        }
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function logPreview(log: AppLogResp) {
  const payload = log.request_payload;
  if (!payload) return "无请求内容";
  if (typeof payload === "string") return truncate(payload);
  const obj = payload as Record<string, unknown>;

  // chat 风格：取最后一条 user 消息
  const messages = obj.messages;
  if (Array.isArray(messages) && messages.length) {
    const lastUser = [...messages]
      .reverse()
      .find((m) => m && typeof m === "object" && (m as Record<string, unknown>).role === "user");
    const target = lastUser ?? messages[messages.length - 1];
    const text = extractText((target as Record<string, unknown>)?.content);
    if (text) return truncate(text);
  }

  const candidate = obj.query ?? obj.question ?? obj.prompt ?? obj.input ?? obj.inputs;
  return truncate(extractText(candidate) || JSON.stringify(payload));
}

function truncate(text: string, max = 140) {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > max ? `${normalized.slice(0, max)}…` : normalized;
}

function openLogDetail(log: AppLogResp) {
  currentLog.value = log;
  logDetailOpen.value = true;
}

function openTestDrawer() {
  testOpen.value = true;
  resetStreamState();
  if (app.value?.app_type === "agent" && !agentTestMessage.value.trim()) {
    agentTestMessage.value = "";
  }
}

function openFlowiseCanvas() {
  const id = app.value?.flowise_chatflow_id;
  if (!id) return;
  // popup 打开 Flowise Agent Flow v2 画布(URL 经 easy-ai 反代,自动带 cookie)
  window.open(`/flowise/v2/agentcanvas/${id}`, "_blank", "noopener");
}

function syncLlmTestInputs() {
  const nextKeys = new Set(
    llmInputVars.value.map((item) => item.name?.trim()).filter((item): item is string => !!item)
  );
  Object.keys(llmTestInputs).forEach((key) => {
    if (!nextKeys.has(key)) {
      delete llmTestInputs[key];
    }
  });
  llmInputVars.value.forEach((item) => {
    const key = item.name?.trim();
    if (!key || key in llmTestInputs) {
      return;
    }
    llmTestInputs[key] = item.type === "number" ? undefined : "";
  });
}

async function loadPageData() {
  const id = route.params.id as string;
  const [{ data: appData }, { data: versionData }, { data: logData }, { data: providerData }] = await Promise.all([
    appApi.getApp(id),
    appApi.listAppVersions(id),
    appApi.listAppLogs(id),
    llmApi.pageProvider({ page_no: 1, page_size: 200 }),
  ]);
  app.value = appData.data;
  versions.value = versionData.data;
  appLogs.value = logData.data;
  providers.value = providerData.data.map((item) => ({ id: item.id, name: item.name }));
  syncLlmTestInputs();
}

function openPublish() {
  publishForm.version = app.value?.current_version ? `${app.value.current_version}.1` : "v1.0.0";
  publishForm.version_note = "";
  publishOpen.value = true;
}

async function doPublish() {
  if (!app.value || !publishForm.version.trim()) return;
  publishing.value = true;
  try {
    await appApi.publishApp(app.value.id, {
      version: publishForm.version,
      version_note: publishForm.version_note || undefined,
    });
    message.success("发布成功");
    publishOpen.value = false;
    await loadPageData();
  } finally {
    publishing.value = false;
  }
}

async function onOffline() {
  if (!app.value) return;
  await appApi.offlineApp(app.value.id);
  message.success("已下线");
  await loadPageData();
}

async function onDelete() {
  if (!app.value) return;
  await appApi.deleteApp(app.value.id);
  message.success("已删除");
  await router.push("/app");
}

function resetStreamState() {
  streamingContent.value = "";
  streamingToolCalls.value = [];
  streamTextBlocks = new Set();
  userMessageText.value = "";
  streamMeta.model = "";
  streamMeta.latency_ms = null;
  streamMeta.tokenUsage = null;
  streamAbort.value = null;
  pendingHitl.value = null;
  pendingHitlRunId.value = null;
  hitlBusy.value = false;
  currentThreadId.value = null;
  hitlTimeoutFlag = false;
  ragReferences.value = [];
}

function handleStreamEvent(evt: SSEEvent) {
  const d = evt.data;
  switch (evt.event) {
    case "run.started": {
      const ext = (d.ext as Record<string, unknown>) || {};
      streamMeta.model = (ext.model as string) || "";
      if (d.thread_id) currentThreadId.value = d.thread_id as string;
      break;
    }
    case "block.started":
      if (d.block_type === "text") {
        streamTextBlocks.add(`${d.message_id}:${d.block_index}`);
      }
      break;
    case "block.delta":
      if (streamTextBlocks.has(`${d.message_id}:${d.block_index}`)) {
        streamingContent.value += (d.delta as string) || "";
      }
      break;
    case "tool.started":
      streamingToolCalls.value.push({
        tool_call_id: (d.tool_call_id as string) || "",
        name: (d.name as string) || "",
        status: "running",
        arguments: d.arguments as Record<string, unknown> | undefined,
      });
      break;
    case "tool.updated": {
      const tc = streamingToolCalls.value.find(
        (t) => t.tool_call_id === (d.tool_call_id as string),
      );
      if (tc) {
        const st = (d.status as string) || "";
        tc.status = st === "completed" ? "done" : st === "failed" ? "error" : "running";
        if (d.result != null) tc.result = (d.result as string) || "";
      }
      break;
    }
    case "hitl.required":
      pendingHitl.value = d as unknown as HitlPayload;
      pendingHitlRunId.value = (d.run_id as string) || null;
      break;
    case "ext.references":
      // RAG 流式专属:富结构参考文档列表
      ragReferences.value = (d.items as AppRunReference[]) ?? [];
      break;
    case "run.finished": {
      const ext = (d.ext as Record<string, unknown>) || {};
      streamMeta.tokenUsage = (ext.usage as TokenUsage) ?? null;
      streamMeta.latency_ms = (ext.latency_ms as number) ?? null;
      break;
    }
    case "run.error":
      message.error((d.message as string) || "执行出错");
      break;
  }
}

function onHitlRespond(action: HitlAction, parameters?: Record<string, unknown>) {
  if (!pendingHitl.value || !currentThreadId.value || !app.value) return;
  if (hitlBusy.value) return;
  hitlBusy.value = true;
  isStreaming.value = true;
  const hitlId = pendingHitl.value.hitl_id;
  hitlTimeoutFlag = false;
  const tc = streamingToolCalls.value.find(
    (t) => t.tool_call_id === pendingHitl.value?.tool_call_id,
  );
  if (tc) tc.status = "done";
  const parentRunId = pendingHitlRunId.value ?? undefined;
  pendingHitl.value = null;
  pendingHitlRunId.value = null;
  streamAbort.value = appApi.testAppHitlRespondStream(
    app.value.id,
    hitlId,
    {
      thread_id: currentThreadId.value,
      ...(parentRunId ? { parent_run_id: parentRunId } : {}),
      outcome: {
        selected: {
          option_id: action,
          ...(action === "modify" && parameters ? { parameters } : {}),
        },
      },
    },
    {
      onEvent: handleStreamEvent,
      onDone() {
        isStreaming.value = false;
        hitlBusy.value = false;
      },
      onError(err) {
        message.error(err.message || "续跑失败");
        isStreaming.value = false;
        hitlBusy.value = false;
      },
    },
  );
}

function onStopStream() {
  streamAbort.value?.abort();
  streamAbort.value = null;
  isStreaming.value = false;
  pendingHitl.value = null;
  hitlBusy.value = false;
}

function truncateToolResult(text: string, max = 200): string {
  return text.length > max ? text.slice(0, max) + "..." : text;
}

function onTestLlm() {
  if (!app.value || app.value.app_type !== "llm") return;
  resetStreamState();
  isStreaming.value = true;

  const inputs = Object.fromEntries(
    Object.entries(llmTestInputs).filter(([, value]) => value !== undefined && value !== "")
  );
  // 构建用户消息文本用于展示
  const parts = Object.entries(inputs).map(([k, v]) => `${k}: ${v}`);
  userMessageText.value = parts.length ? parts.join("\n") : "(默认 Prompt)";

  streamAbort.value = appApi.testAppStream(app.value.id, { inputs }, {
    onEvent: handleStreamEvent,
    onDone() {
      isStreaming.value = false;
    },
    onError(err) {
      message.error(err.message || "测试请求失败");
      isStreaming.value = false;
    },
  });
}

function dispatchTestRun() {
  if (!app.value) return;
  if (app.value.app_type === "llm") return onTestLlm();
  if (app.value.app_type === "agent") return onTestAgent();
  if (app.value.app_type === "rag") return onTestRag();
}

// M2.2 后改走 SSE 流, 体验与 LLM/Agent 测试一致;references 通过新
// SSE 事件 'references' 推。后端 RagApp.stream 已支持。
function onTestRag() {
  if (!app.value || app.value.app_type !== "rag") return;
  const q = ragTestQuery.value.trim();
  if (!q) {
    message.warning("请输入测试问题");
    return;
  }
  resetStreamState();
  isStreaming.value = true;
  userMessageText.value = q;
  streamAbort.value = appApi.testAppStream(
    app.value.id,
    { messages: [{ role: "user", content: q }] },
    {
      onEvent: handleStreamEvent,
      onDone() {
        isStreaming.value = false;
      },
      onError(err) {
        message.error(err.message || "测试请求失败");
        isStreaming.value = false;
      },
    },
  );
}

function openRefPreview(ref: AppRunReference) {
  if (!ref.kb_id || !ref.doc_id) {
    message.warning("缺少 kb_id / doc_id, 无法跳转预览");
    return;
  }
  const url = router.resolve({
    name: "knowledge-doc-preview",
    params: { kbId: ref.kb_id, docId: ref.doc_id },
  }).href;
  window.open(url, "_blank");
}

function onTestAgent() {
  if (!app.value || app.value.app_type !== "agent") return;
  if (!agentTestMessage.value.trim()) {
    message.warning("请输入测试消息");
    return;
  }
  resetStreamState();
  isStreaming.value = true;
  userMessageText.value = agentTestMessage.value.trim();

  streamAbort.value = appApi.testAppStream(
    app.value.id,
    { messages: [{ role: "user", content: agentTestMessage.value.trim() }] },
    {
      onEvent: handleStreamEvent,
      onDone() {
        isStreaming.value = false;
      },
      onError(err) {
        message.error(err.message || "测试请求失败");
        isStreaming.value = false;
      },
    },
  );
}

onMounted(() => {
  void loadPageData();
});
</script>

<style scoped>
.detail-page {
  min-height: 0;
}

.back-btn {
  padding: 0;
  margin-bottom: 16px;
}

.draft-banner {
  margin-bottom: 16px;
  border-radius: 12px;
}

.hero-card,
.panel-card {
  border: 1px solid var(--surface-card-border);
  border-radius: 22px;
  background: var(--surface-card-bg);
  box-shadow: var(--surface-card-shadow);
}

.hero-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 24px;
}

.hero-main {
  flex: 1;
  min-width: 0;
}

.hero-top {
  display: flex;
  gap: 16px;
}

.hero-icon {
  width: 60px;
  height: 60px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  flex-shrink: 0;
}

.app-type--rag {
  background: var(--color-info-bg);
}

.app-type--llm {
  background: var(--color-success-bg);
}

.app-type--nl2sql {
  background: var(--color-cyan-bg);
}

.app-type--agent {
  background: var(--color-violet-bg);
}

.app-type--agent_flow {
  background: var(--color-warning-bg);
}

.hero-title-wrap {
  flex: 1;
  min-width: 0;
}

.hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.app-type-tag,
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.app-type-tag.app-type--rag {
  color: var(--color-info-strong);
}

.app-type-tag.app-type--llm {
  color: var(--color-success-strong);
}

.app-type-tag.app-type--nl2sql {
  color: var(--color-cyan-text);
}

.app-type-tag.app-type--agent {
  color: var(--color-accent);
}

.app-type-tag.app-type--agent_flow {
  color: var(--color-warning-strong);
}

.status--draft {
  background: var(--color-neutral-bg);
  color: var(--color-text-tertiary);
}

.status--published {
  background: var(--color-success-bg);
  color: var(--color-success-strong);
}

.status--offline {
  background: var(--color-border);
  color: var(--color-text-tertiary);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}

.hero-title {
  margin: 12px 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
}

.hero-desc {
  margin: 0;
  color: var(--color-text-tertiary);
  line-height: 1.8;
}

.hero-cat-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 22px;
}

.metric-card {
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
}

.metric-label {
  display: block;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.metric-value {
  display: block;
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
}

.metric-value--small {
  font-size: 15px;
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

/* ── 测试面板 ── */
.test-chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

/* 输入 + 操作合并区 */
.test-composer {
  flex-shrink: 0;
  margin: 16px 20px 0;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--surface-strong);
  box-shadow: var(--shadow-card-sm);
  overflow: hidden;
}

.test-composer-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px;
}

.test-form-item {
  margin-bottom: 0;
}

.test-composer-hint {
  padding: 14px 16px;
  font-size: 13px;
  color: var(--color-text-quaternary);
}

.test-composer-textarea {
  border: none !important;
  box-shadow: none !important;
  resize: none;
  padding: 14px 16px;
  font-size: 13px;
}

.test-composer-textarea:focus {
  box-shadow: none !important;
}

.test-composer-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-top: 1px solid var(--color-border);
  background: var(--surface-muted);
}

.test-composer-spacer {
  flex: 1;
}

.test-meta-tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 6px;
  background: var(--color-violet-bg);
  color: var(--color-accent);
  font-size: 11px;
  font-weight: 600;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 消息时间轴 */
.test-timeline {
  flex: 1;
  padding: 20px 20px 20px 24px;
  display: flex;
  flex-direction: column;
}

.tl-item {
  display: flex;
  gap: 0;
  min-height: 0;
}

.tl-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
  padding-top: 6px;
}

.tl-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  flex-shrink: 0;
  border: 2px solid var(--color-border-secondary);
  background: var(--color-bg-elevated);
}

.tl-dot--human  { border-color: var(--color-info-strong); background: var(--color-info-bg-strong); }
.tl-dot--ai     { border-color: var(--color-accent); background: var(--color-violet-bg); }
.tl-dot--tool   { border-color: var(--color-warning); background: var(--color-warning-bg-strong); }
.tl-dot--hitl   { border-color: var(--color-error); background: var(--color-error-bg-strong); }
.tl-dot--system { border-color: var(--color-text-tertiary); background: var(--color-neutral-bg); }
.tl-dot--done   { border-color: var(--color-success); background: var(--color-success-bg-strong); }

.tl-line {
  flex: 1;
  width: 2px;
  min-height: 16px;
  background: var(--surface-timeline-line);
  margin: 4px 0;
}

.tl-line--last {
  background: transparent;
}

.tl-body {
  flex: 1;
  min-width: 0;
  padding-bottom: 14px;
  padding-left: 10px;
}

.tl-item--stats .tl-body {
  padding-bottom: 0;
}

/* 统计 */
.test-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: var(--color-text-quaternary);
}

/* RAG references */
.rag-refs {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--surface-divider, #eee);
}
.rag-refs-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.rag-refs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rag-ref-card {
  padding: 10px 12px;
  border: 1px solid var(--surface-divider, #eee);
  border-radius: 8px;
  background: var(--color-bg-elevated, rgba(0, 0, 0, 0.02));
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.rag-ref-card:hover {
  border-color: var(--color-primary, #1677ff);
  background: var(--color-info-bg, rgba(22, 119, 255, 0.05));
}
.rag-ref-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 4px;
}
.rag-ref-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--color-text);
}
.rag-ref-sim {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.rag-ref-snippet {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  max-height: 4.5em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.rag-ref-foot {
  margin-top: 6px;
}
.rag-ref-code {
  display: inline-block;
  font-family: ui-monospace, "SFMono-Regular", Menlo, monospace;
  font-size: 11px;
  color: var(--color-text-tertiary);
  background: rgba(0, 0, 0, 0.04);
  padding: 1px 6px;
  border-radius: 3px;
}

/* 空状态 */
.test-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
}

.test-empty-icon {
  font-size: 36px;
  opacity: 0.4;
}

.test-empty-text {
  font-size: 13px;
  color: var(--color-text-quaternary);
}

/* 消息卡片补充 */
.msg-tool-status {
  display: flex;
  align-items: center;
}

.msg-tool-status-done {
  font-size: 11px;
  color: var(--color-success-text);
  font-weight: 600;
}

.msg-content--tool-result {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--color-success-bg);
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

.detail-tabs {
  margin-top: 18px;
}

.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.panel-card {
  padding: 20px;
}

.panel-card--full {
  margin-top: 16px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
}

.panel-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.kv-item {
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: var(--surface-muted-hover);
}

.kv-label {
  display: block;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.kv-value {
  display: block;
  margin-top: 8px;
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.7;
}

.agent-flow-desc {
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: var(--surface-muted-hover);
}

.agent-flow-desc-label {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.agent-flow-desc-text {
  margin-top: 6px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text);
  white-space: pre-wrap;
}

.empty-note {
  font-size: 13px;
  color: var(--color-text-quaternary);
}

.version-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.version-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: var(--surface-muted-hover);
}

.version-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
}

.version-note {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.version-time {
  font-size: 12px;
  color: var(--color-text-quaternary);
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.log-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: var(--surface-muted-hover);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}

.log-row:hover {
  border-color: var(--color-info-border);
  box-shadow: var(--shadow-card-sm);
  transform: translateY(-1px);
}

.log-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.log-preview {
  font-size: 13px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.log-arrow {
  color: var(--color-text-quaternary);
  font-size: 12px;
}

.log-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.log-detail-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.log-meta,
.log-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.log-type {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--color-neutral-bg);
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.log-type--test {
  background: var(--color-warning-bg-strong);
  color: var(--color-warning-text);
}

.log-type--chat {
  background: var(--color-success-bg-strong);
  color: var(--color-success-text);
}

.log-type--api {
  background: var(--color-info-bg-strong);
  color: var(--color-info-strong);
}

.log-status {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.log-status--success {
  background: var(--color-success-bg);
  color: var(--color-success-text);
}

.log-status--error {
  background: var(--color-error-bg);
  color: var(--color-error-text);
}

.log-time,
.log-side {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.log-error {
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--color-error-bg);
  color: var(--color-error-text);
  font-size: 12px;
  line-height: 1.6;
}

/* 概览 */
.log-overview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border-radius: 14px;
  background: var(--surface-muted-hover);
  border: 1px solid var(--color-border);
}

.log-overview-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}

.log-overview-label {
  flex-shrink: 0;
  width: 72px;
  color: var(--color-text-quaternary);
  font-weight: 600;
}

.log-overview-value {
  color: var(--color-text);
}

.log-overview-mono {
  font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  font-size: 12px;
  word-break: break-all;
}

/* 历史消息时间轴 */
.log-timeline {
  display: flex;
  flex-direction: column;
  padding-left: 4px;
}

.msg-card {
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}

.msg-card--human {
  border-left: 3px solid var(--color-info-strong);
}

.msg-card--ai {
  border-left: 3px solid var(--color-accent);
}

.msg-card--tool {
  border-left: 3px solid var(--color-warning);
}

.msg-card--system {
  border-left: 3px solid var(--color-text-tertiary);
}

.msg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.msg-type-badge {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.msg-type-badge--human {
  background: var(--color-info-bg);
  color: var(--color-info-strong);
}

.msg-type-badge--ai {
  background: var(--color-violet-bg);
  color: var(--color-accent);
}

.msg-type-badge--tool {
  background: var(--color-warning-bg);
  color: var(--color-warning-text);
}

.msg-type-badge--system {
  background: var(--color-neutral-bg);
  color: var(--color-text-secondary);
}

.msg-tokens {
  font-size: 11px;
  color: var(--color-text-quaternary);
}

.msg-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-secondary);
  word-break: break-word;
}

.msg-content :deep(p) {
  margin: 0 0 8px;
}

.msg-content :deep(p:last-child) {
  margin-bottom: 0;
}

.msg-content :deep(h1),
.msg-content :deep(h2),
.msg-content :deep(h3) {
  margin: 12px 0 6px;
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
}

.msg-content :deep(ul),
.msg-content :deep(ol) {
  margin: 4px 0 8px;
  padding-left: 20px;
}

.msg-content :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--color-neutral-bg);
  font-size: 12px;
  font-family: "SF Mono", "Fira Code", "Consolas", monospace;
}

.msg-content :deep(pre) {
  margin: 8px 0;
  padding: 12px;
  border-radius: 10px;
  background: var(--surface-code);
  color: var(--color-code-text);
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
}

.msg-content :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
}

.msg-content--empty {
  color: var(--color-text-quaternary);
  font-style: italic;
}

.msg-tool-calls {
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg-tool-call {
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
}

.msg-tool-name {
  display: inline-block;
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-warning-text);
}

.msg-tool-args {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.log-payload-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.config-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-block {
  min-width: 0;
}

.config-label,
.doc-title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-secondary);
}

.prompt-block {
  margin: 0;
  padding: 16px;
  border-radius: 14px;
  background: var(--surface-code);
  color: var(--color-code-text);
  font-size: 12px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.endpoint-box {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--surface-muted-hover);
  border: 1px solid var(--color-border);
}

.endpoint-box--soft {
  margin-top: 8px;
}

.endpoint-method {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  height: 24px;
  border-radius: 999px;
  background: var(--color-info-bg);
  color: var(--color-info-strong);
  font-size: 11px;
  font-weight: 700;
}

.doc-block {
  margin-top: 16px;
}

@media (max-width: 1080px) {
  .hero-card {
    flex-direction: column;
  }

  .hero-metrics,
  .overview-grid,
  .kv-grid,
  .log-payload-grid {
    grid-template-columns: 1fr;
  }
}
</style>
