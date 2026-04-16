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
        <a-button type="primary" size="small" @click="openPublish">发布应用</a-button>
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
        <a-button @click="router.push(`/app/${app.id}/edit`)">编辑</a-button>
        <a-button
          v-if="app.app_type === 'agent_flow'"
          type="primary"
          :disabled="!app.flowise_chatflow_id"
          :title="app.flowise_chatflow_id ? '' : '未关联 Flowise 画布'"
          @click="openFlowiseCanvas"
        >
          打开画布
        </a-button>
        <a-button v-if="['llm', 'agent'].includes(app.app_type)" @click="openTestDrawer">测试</a-button>
        <a-button v-if="app.app_status === 'published'" @click="onOffline">下线</a-button>
        <a-button v-if="app.app_status === 'offline'" type="primary" @click="openPublish">上线</a-button>
        <a-button v-if="app.app_status === 'draft'" type="primary" @click="openPublish">发布应用</a-button>
        <a-button v-if="app.app_status === 'published'" type="primary" @click="openPublish">发布新版本</a-button>
        <a-popconfirm title="确定删除该应用？" @confirm="onDelete">
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
      <template v-if="['llm', 'agent'].includes(app?.app_type ?? '')">
        <div class="test-chat-body">
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
                @click="app?.app_type === 'llm' ? onTestLlm() : onTestAgent()"
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
                    <span class="msg-type-badge msg-type-badge--tool">{{ msgTypeLabel.tool }}</span>
                    <span class="msg-tool-status">
                      <a-spin v-if="tc.status === 'running'" size="small" />
                      <span v-else class="msg-tool-status-done">done</span>
                    </span>
                  </div>
                  <div class="msg-tool-calls">
                    <div class="msg-tool-call">
                      <span class="msg-tool-name">{{ tc.name }}</span>
                      <pre v-if="tc.arguments && Object.keys(tc.arguments).length" class="msg-tool-args">{{ stringifyJson(tc.arguments) }}</pre>
                    </div>
                  </div>
                  <div v-if="tc.result" class="msg-content msg-content--tool-result">{{ truncateToolResult(tc.result, 500) }}</div>
                </div>
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
            <div class="test-empty-icon">{{ app?.app_type === 'agent' ? '🤖' : '✨' }}</div>
            <div class="test-empty-text">{{ app?.app_type === 'agent' ? '输入消息开始与 Agent 对话' : '填写输入变量后点击运行' }}</div>
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
                      <span class="msg-tool-name">{{ tc.name }}</span>
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
import { marked } from "marked";
import * as appApi from "@/api/app";
import * as llmApi from "@/api/llm";
import type { AppLogResp, AppResp, AppVersionResp } from "@/api/types";
import type { SSEEvent } from "@/api/sse";
import { formatMs } from "@/utils/time";

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
const logDetailOpen = ref(false);
const currentLog = ref<AppLogResp | null>(null);
const logViewMode = ref<"formatted" | "raw">("formatted");
const publishForm = reactive({ version: "", version_note: "" });

// 流式输出状态
interface StreamingToolCall {
  tool_call_id: string;
  name: string;
  status: "running" | "done";
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
const streamAbort = ref<{ abort: () => void } | null>(null);
const userMessageText = ref("");
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

function renderMarkdown(text: string): string {
  return marked(text) as string;
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
  userMessageText.value = "";
  streamMeta.model = "";
  streamMeta.latency_ms = null;
  streamMeta.tokenUsage = null;
  streamAbort.value = null;
}

function handleStreamEvent(evt: SSEEvent) {
  switch (evt.event) {
    case "metadata":
      streamMeta.model = (evt.data.model as string) || "";
      break;
    case "token":
      streamingContent.value += (evt.data.content as string) || "";
      break;
    case "tool_call_start":
      streamingToolCalls.value.push({
        tool_call_id: (evt.data.tool_call_id as string) || "",
        name: (evt.data.name as string) || "",
        status: "running",
        arguments: evt.data.arguments as Record<string, unknown> | undefined,
      });
      break;
    case "tool_call_end": {
      const id = evt.data.tool_call_id as string;
      const tc = streamingToolCalls.value.find((t) => t.tool_call_id === id);
      if (tc) {
        tc.status = "done";
        tc.result = (evt.data.result as string) || "";
      }
      break;
    }
    case "message_complete":
      streamMeta.tokenUsage = (evt.data.usage as TokenUsage) ?? null;
      break;
    case "done":
      streamMeta.latency_ms = (evt.data.latency_ms as number) ?? null;
      break;
    case "error":
      message.error((evt.data.message as string) || "执行出错");
      break;
  }
}

function onStopStream() {
  streamAbort.value?.abort();
  streamAbort.value = null;
  isStreaming.value = false;
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
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.86) 100%);
  box-shadow:
    0 24px 48px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
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
  background: rgba(59, 130, 246, 0.12);
}

.app-type--llm {
  background: rgba(16, 185, 129, 0.12);
}

.app-type--nl2sql {
  background: rgba(6, 182, 212, 0.12);
}

.app-type--agent {
  background: rgba(139, 92, 246, 0.12);
}

.app-type--agent_flow {
  background: rgba(245, 158, 11, 0.12);
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
  color: #2563eb;
}

.app-type-tag.app-type--llm {
  color: #059669;
}

.app-type-tag.app-type--nl2sql {
  color: #0891b2;
}

.app-type-tag.app-type--agent {
  color: #7c3aed;
}

.app-type-tag.app-type--agent_flow {
  color: #d97706;
}

.status--draft {
  background: rgba(148, 163, 184, 0.12);
  color: #64748b;
}

.status--published {
  background: rgba(16, 185, 129, 0.12);
  color: #059669;
}

.status--offline {
  background: rgba(226, 232, 240, 0.9);
  color: #64748b;
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
  color: #0f172a;
}

.hero-desc {
  margin: 0;
  color: #64748b;
  line-height: 1.8;
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
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(226, 232, 240, 0.8);
}

.metric-label {
  display: block;
  font-size: 12px;
  color: #64748b;
}

.metric-value {
  display: block;
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
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
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
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
  color: #94a3b8;
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
  border-top: 1px solid rgba(226, 232, 240, 0.6);
  background: rgba(248, 250, 252, 0.5);
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
  background: rgba(139, 92, 246, 0.08);
  color: #7c3aed;
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
  border: 2px solid #cbd5e1;
  background: #fff;
}

.tl-dot--human  { border-color: #2563eb; background: rgba(37, 99, 235, 0.15); }
.tl-dot--ai     { border-color: #8b5cf6; background: rgba(139, 92, 246, 0.15); }
.tl-dot--tool   { border-color: #f59e0b; background: rgba(245, 158, 11, 0.15); }
.tl-dot--system { border-color: #64748b; background: rgba(100, 116, 139, 0.15); }
.tl-dot--done   { border-color: #10b981; background: rgba(16, 185, 129, 0.15); }

.tl-line {
  flex: 1;
  width: 2px;
  min-height: 16px;
  background: linear-gradient(180deg, rgba(203, 213, 225, 0.7) 0%, rgba(203, 213, 225, 0.2) 100%);
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
  color: #94a3b8;
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
  color: #94a3b8;
}

/* 消息卡片补充 */
.msg-tool-status {
  display: flex;
  align-items: center;
}

.msg-tool-status-done {
  font-size: 11px;
  color: #15803d;
  font-weight: 600;
}

.msg-content--tool-result {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(16, 185, 129, 0.06);
  font-size: 12px;
  color: #334155;
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
  color: #0f172a;
}

.panel-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: #64748b;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.kv-item {
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(226, 232, 240, 0.8);
  background: rgba(248, 250, 252, 0.84);
}

.kv-label {
  display: block;
  font-size: 12px;
  color: #64748b;
}

.kv-value {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  font-size: 14px;
  line-height: 1.7;
}

.agent-flow-desc {
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid rgba(226, 232, 240, 0.8);
  background: rgba(248, 250, 252, 0.84);
}

.agent-flow-desc-label {
  font-size: 12px;
  color: #64748b;
}

.agent-flow-desc-text {
  margin-top: 6px;
  font-size: 14px;
  line-height: 1.7;
  color: #0f172a;
  white-space: pre-wrap;
}

.empty-note {
  font-size: 13px;
  color: #94a3b8;
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
  border: 1px solid rgba(226, 232, 240, 0.8);
  background: rgba(248, 250, 252, 0.84);
}

.version-name {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.version-note {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.version-time {
  font-size: 12px;
  color: #94a3b8;
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
  border: 1px solid rgba(226, 232, 240, 0.8);
  background: rgba(248, 250, 252, 0.84);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}

.log-row:hover {
  border-color: rgba(37, 99, 235, 0.45);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
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
  color: #475569;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.log-arrow {
  color: #94a3b8;
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
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.log-type--test {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}

.log-type--chat {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.log-type--api {
  background: rgba(37, 99, 235, 0.14);
  color: #1d4ed8;
}

.log-status {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.log-status--success {
  background: rgba(34, 197, 94, 0.12);
  color: #15803d;
}

.log-status--error {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.log-time,
.log-side {
  font-size: 12px;
  color: #64748b;
}

.log-error {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.08);
  color: #b91c1c;
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
  background: rgba(248, 250, 252, 0.84);
  border: 1px solid rgba(226, 232, 240, 0.8);
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
  color: #94a3b8;
  font-weight: 600;
}

.log-overview-value {
  color: #1e293b;
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
  border: 1px solid rgba(226, 232, 240, 0.8);
  background: #fff;
}

.msg-card--human {
  border-left: 3px solid #2563eb;
}

.msg-card--ai {
  border-left: 3px solid #8b5cf6;
}

.msg-card--tool {
  border-left: 3px solid #f59e0b;
}

.msg-card--system {
  border-left: 3px solid #64748b;
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
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
}

.msg-type-badge--ai {
  background: rgba(139, 92, 246, 0.12);
  color: #6d28d9;
}

.msg-type-badge--tool {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.msg-type-badge--system {
  background: rgba(100, 116, 139, 0.12);
  color: #475569;
}

.msg-tokens {
  font-size: 11px;
  color: #94a3b8;
}

.msg-content {
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
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
  color: #1e293b;
}

.msg-content :deep(ul),
.msg-content :deep(ol) {
  margin: 4px 0 8px;
  padding-left: 20px;
}

.msg-content :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.06);
  font-size: 12px;
  font-family: "SF Mono", "Fira Code", "Consolas", monospace;
}

.msg-content :deep(pre) {
  margin: 8px 0;
  padding: 12px;
  border-radius: 10px;
  background: #0f172a;
  color: #e2e8f0;
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
  color: #94a3b8;
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
  background: rgba(245, 158, 11, 0.06);
  border: 1px solid rgba(245, 158, 11, 0.18);
}

.msg-tool-name {
  display: inline-block;
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 700;
  color: #b45309;
}

.msg-tool-args {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: #475569;
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
  color: #475569;
}

.prompt-block {
  margin: 0;
  padding: 16px;
  border-radius: 14px;
  background: #0f172a;
  color: #e2e8f0;
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
  background: rgba(248, 250, 252, 0.84);
  border: 1px solid rgba(226, 232, 240, 0.8);
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
  background: rgba(37, 99, 235, 0.12);
  color: #2563eb;
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
