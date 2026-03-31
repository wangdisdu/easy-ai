<template>
  <div class="login-view">
    <section class="login-hero" aria-hidden="true">
      <div class="login-hero-orbit login-hero-orbit--a" />
      <div class="login-hero-orbit login-hero-orbit--b" />
      <div class="login-hero-grid" />
      <div class="login-hero-glow login-hero-glow--a" />
      <div class="login-hero-glow login-hero-glow--b" />
      <div class="login-hero-content">
        <p class="login-hero-tag">ENTERPRISE AI CONTROL CENTER</p>
        <h1 class="login-hero-title">智瞻 AI</h1>
        <p class="login-hero-desc">面向企业场景的 AI 平台，统一承载智能助手、应用编排、知识资产与平台治理能力。</p>
        <div class="login-hero-badge-row">
          <span class="login-hero-badge">Agent Workspace</span>
          <span class="login-hero-badge">Knowledge Fabric</span>
          <span class="login-hero-badge">Secure Governance</span>
        </div>
        <ul class="login-hero-meta">
          <li><span class="login-hero-dot" />统一身份认证</li>
          <li><span class="login-hero-dot" />企业级权限控制</li>
          <li><span class="login-hero-dot" />模型与应用治理</li>
        </ul>
      </div>
    </section>

    <section class="login-aside">
      <div class="login-panel">
        <div class="login-panel-frame" />
        <div class="login-panel-scan" aria-hidden="true" />
        <header class="login-panel-head">
          <p class="login-panel-kicker">CONSOLE ACCESS</p>
          <h2 class="login-panel-title">登录智瞻 AI</h2>
          <p class="login-panel-sub">使用企业账号进入平台控制台，访问智能助手、应用工厂与平台管理能力。</p>
        </header>

        <form class="login-form" @submit.prevent="onSubmit">
          <div class="login-field">
            <label class="login-label" for="login-account">账号标识</label>
            <input
              id="login-account"
              v-model="form.account"
              class="login-input"
              type="text"
              name="username"
              autocomplete="username"
              placeholder="请输入企业账号 / 工号"
            />
          </div>
          <div class="login-field">
            <label class="login-label" for="login-passwd">登录密码</label>
            <input
              id="login-passwd"
              v-model="form.passwd"
              class="login-input"
              type="password"
              name="password"
              autocomplete="current-password"
              placeholder="请输入登录密码"
            />
          </div>
          <p v-if="fieldError" class="login-hint login-hint--err">{{ fieldError }}</p>
          <button class="login-submit" type="submit" :disabled="loading">
            <span v-if="loading" class="login-submit-loading" aria-hidden="true" />
            <span>{{ loading ? "身份校验中…" : "进入智瞻 AI" }}</span>
          </button>
        </form>
        <p class="login-panel-note">建议使用企业统一分配账号登录，所有操作将纳入平台审计记录。</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { message } from "ant-design-vue";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const loading = ref(false);
const fieldError = ref("");

const form = reactive({
  account: "",
  passwd: "",
});

async function onSubmit() {
  fieldError.value = "";
  if (!form.account.trim()) {
    fieldError.value = "请填写账号";
    return;
  }
  if (!form.passwd) {
    fieldError.value = "请填写密码";
    return;
  }
  loading.value = true;
  try {
    await auth.login(form.account.trim(), form.passwd);
    message.success("登录成功");
    const redirect = (route.query.redirect as string) || "/";
    await router.replace(redirect);
  } catch {
    /* 错误已在 axios 拦截器提示 */
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500;600&display=swap");

.login-view {
  min-height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(440px, 560px);
  font-family: "IBM Plex Sans", "PingFang SC", "Noto Sans SC", sans-serif;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.2), transparent 28%),
    radial-gradient(circle at 85% 85%, rgba(124, 58, 237, 0.16), transparent 30%),
    #050810;
  color: #e8eef8;
}

@media (max-width: 960px) {
  .login-view {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }
}

.login-hero {
  position: relative;
  overflow: hidden;
  padding: clamp(32px, 6vw, 64px);
  border-right: 1px solid rgba(59, 130, 246, 0.12);
}

@media (max-width: 960px) {
  .login-hero {
    border-right: none;
    border-bottom: 1px solid rgba(59, 130, 246, 0.12);
    min-height: 220px;
  }
}

.login-hero-orbit {
  position: absolute;
  border-radius: 999px;
  border: 1px solid rgba(96, 165, 250, 0.12);
  pointer-events: none;
}

.login-hero-orbit--a {
  width: 520px;
  height: 520px;
  top: -220px;
  left: -120px;
  transform: rotate(12deg);
}

.login-hero-orbit--b {
  width: 340px;
  height: 340px;
  right: 8%;
  bottom: -120px;
  border-color: rgba(167, 139, 250, 0.14);
}

.login-hero-grid {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(59, 130, 246, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59, 130, 246, 0.06) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse 80% 70% at 30% 40%, black 20%, transparent 70%);
}

.login-hero-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.45;
  pointer-events: none;
}

.login-hero-glow--a {
  width: 420px;
  height: 420px;
  top: -120px;
  left: -80px;
  background: #2563eb;
}

.login-hero-glow--b {
  width: 320px;
  height: 320px;
  bottom: -80px;
  right: 10%;
  background: #7c3aed;
}

.login-hero-content {
  position: relative;
  z-index: 1;
  max-width: 520px;
  padding-top: clamp(12px, 5vh, 60px);
}

.login-hero-tag {
  margin: 0 0 16px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.28em;
  color: #60a5fa;
}

.login-hero-title {
  margin: 0 0 12px;
  font-family: "JetBrains Mono", monospace;
  font-size: clamp(2.5rem, 5vw, 3.25rem);
  font-weight: 600;
  letter-spacing: -0.02em;
  background: linear-gradient(120deg, #f0f4ff 0%, #93c5fd 45%, #a78bfa 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.login-hero-desc {
  margin: 0 0 28px;
  max-width: 560px;
  font-size: 15px;
  line-height: 1.75;
  color: rgba(200, 214, 236, 0.76);
}

.login-hero-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 26px;
}

.login-hero-badge {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(96, 165, 250, 0.18);
  background: rgba(15, 23, 42, 0.4);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: rgba(191, 219, 254, 0.9);
}

.login-hero-meta {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 16px 24px;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  color: rgba(148, 176, 214, 0.85);
}

.login-hero-meta li {
  display: flex;
  align-items: center;
  gap: 8px;
}

.login-hero-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 12px #34d399;
  animation: pulse-dot 2.2s ease-in-out infinite;
}

.login-aside {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(24px, 5vw, 48px);
  background:
    linear-gradient(180deg, rgba(6, 10, 20, 0.94) 0%, rgba(4, 8, 18, 1) 100%);
}

.login-panel {
  position: relative;
  width: 100%;
  max-width: 520px;
  padding: 48px 44px 44px;
  background:
    linear-gradient(180deg, rgba(12, 18, 32, 0.88) 0%, rgba(8, 14, 28, 0.78) 100%);
  border: 1px solid rgba(99, 140, 220, 0.24);
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.4), 0 24px 64px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  overflow: hidden;
}

.login-panel-frame {
  pointer-events: none;
  position: absolute;
  inset: 10px;
  border: 1px solid rgba(59, 130, 246, 0.08);
  border-radius: 14px;
}

.login-panel-frame::before,
.login-panel-frame::after {
  content: "";
  position: absolute;
  width: 12px;
  height: 12px;
  border-color: #3b82f6;
  border-style: solid;
  opacity: 0.7;
}

.login-panel-frame::before {
  top: -1px;
  left: -1px;
  border-width: 2px 0 0 2px;
}

.login-panel-frame::after {
  bottom: -1px;
  right: -1px;
  border-width: 0 2px 2px 0;
}

.login-panel-scan {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(180deg, rgba(56, 189, 248, 0.08), transparent 18%, transparent 82%, rgba(124, 58, 237, 0.08));
  mix-blend-mode: screen;
}

.login-panel-head {
  margin-bottom: 36px;
  position: relative;
  z-index: 1;
}

.login-panel-kicker {
  margin: 0 0 8px;
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  letter-spacing: 0.35em;
  color: #64748b;
}

.login-panel-title {
  margin: 0 0 8px;
  font-size: 26px;
  font-weight: 600;
  color: #f1f5f9;
}

.login-panel-sub {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: rgba(148, 163, 184, 0.9);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 22px;
  position: relative;
  z-index: 1;
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.login-label {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #94a3b8;
}

.login-input {
  width: 100%;
  box-sizing: border-box;
  height: 52px;
  padding: 0 18px;
  font-family: "JetBrains Mono", "IBM Plex Sans", monospace;
  font-size: 14px;
  color: #e2e8f0;
  background: rgba(5, 8, 16, 0.72);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 14px;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.login-input::placeholder {
  color: #475569;
}

.login-input:focus {
  border-color: rgba(59, 130, 246, 0.65);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15), 0 0 24px rgba(59, 130, 246, 0.12);
}

.login-hint {
  margin: -8px 0 0;
  font-size: 12px;
}

.login-hint--err {
  color: #f87171;
  font-family: "JetBrains Mono", monospace;
}

.login-submit {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  height: 54px;
  border: none;
  border-radius: 14px;
  font-family: "JetBrains Mono", monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #0f172a;
  cursor: pointer;
  background: linear-gradient(105deg, #67e8f9 0%, #3b82f6 42%, #7c3aed 100%);
  box-shadow: 0 10px 30px rgba(59, 130, 246, 0.28);
  transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
}

.login-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 14px 36px rgba(59, 130, 246, 0.38);
}

.login-submit:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.login-submit-loading {
  display: inline-block;
  width: 14px;
  height: 14px;
  margin-right: 10px;
  vertical-align: middle;
  border: 2px solid rgba(15, 23, 42, 0.25);
  border-top-color: #0f172a;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.login-panel-note {
  position: relative;
  z-index: 1;
  margin: 18px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(148, 163, 184, 0.82);
}

@keyframes pulse-dot {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(0.85);
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
