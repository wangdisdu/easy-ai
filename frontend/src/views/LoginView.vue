<template>
  <div class="login-view">
    <section class="login-hero" aria-hidden="true">
      <div class="login-hero-grid" />
      <div class="login-hero-glow login-hero-glow--a" />
      <div class="login-hero-glow login-hero-glow--b" />
      <div class="login-hero-content">
        <p class="login-hero-tag">SECURE ACCESS GATEWAY</p>
        <h1 class="login-hero-title">easy-ai</h1>
        <p class="login-hero-desc">企业智能应用平台 · 统一身份与权限</p>
        <ul class="login-hero-meta">
          <li><span class="login-hero-dot" />链路加密</li>
          <li><span class="login-hero-dot" />会话令牌</li>
          <li><span class="login-hero-dot" />审计就绪</li>
        </ul>
      </div>
    </section>

    <section class="login-aside">
      <div class="login-panel">
        <div class="login-panel-frame" />
        <header class="login-panel-head">
          <p class="login-panel-kicker">AUTHENTICATION</p>
          <h2 class="login-panel-title">系统登录</h2>
          <p class="login-panel-sub">请输入控制台账号与密码</p>
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
              placeholder="account / 工号"
            />
          </div>
          <div class="login-field">
            <label class="login-label" for="login-passwd">访问密钥</label>
            <input
              id="login-passwd"
              v-model="form.passwd"
              class="login-input"
              type="password"
              name="password"
              autocomplete="current-password"
              placeholder="••••••••"
            />
          </div>
          <p v-if="fieldError" class="login-hint login-hint--err">{{ fieldError }}</p>
          <button class="login-submit" type="submit" :disabled="loading">
            <span v-if="loading" class="login-submit-loading" aria-hidden="true" />
            <span>{{ loading ? "校验中…" : "进入控制台" }}</span>
          </button>
        </form>
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
  background: #050810;
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
  font-size: 15px;
  line-height: 1.6;
  color: rgba(200, 214, 236, 0.72);
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
  background: linear-gradient(180deg, #080c14 0%, #050810 100%);
}

.login-panel {
  position: relative;
  width: 100%;
  max-width: 520px;
  padding: 48px 44px 44px;
  background: rgba(12, 18, 32, 0.72);
  border: 1px solid rgba(99, 140, 220, 0.22);
  border-radius: 4px;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.4), 0 24px 64px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
}

.login-panel-frame {
  pointer-events: none;
  position: absolute;
  inset: 10px;
  border: 1px solid rgba(59, 130, 246, 0.08);
  border-radius: 2px;
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

.login-panel-head {
  margin-bottom: 36px;
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
  font-size: 22px;
  font-weight: 600;
  color: #f1f5f9;
}

.login-panel-sub {
  margin: 0;
  font-size: 13px;
  color: rgba(148, 163, 184, 0.9);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 22px;
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
  height: 48px;
  padding: 0 16px;
  font-family: "JetBrains Mono", "IBM Plex Sans", monospace;
  font-size: 14px;
  color: #e2e8f0;
  background: rgba(5, 8, 16, 0.85);
  border: 1px solid rgba(71, 85, 105, 0.55);
  border-radius: 2px;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.login-input::placeholder {
  color: #475569;
}

.login-input:focus {
  border-color: rgba(59, 130, 246, 0.65);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15), 0 0 24px rgba(59, 130, 246, 0.08);
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
  height: 50px;
  border: none;
  border-radius: 2px;
  font-family: "JetBrains Mono", monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #0f172a;
  cursor: pointer;
  background: linear-gradient(105deg, #38bdf8 0%, #3b82f6 48%, #6366f1 100%);
  box-shadow: 0 4px 24px rgba(59, 130, 246, 0.35);
  transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
}

.login-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 32px rgba(59, 130, 246, 0.45);
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
