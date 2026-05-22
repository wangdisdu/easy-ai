import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const APP_ANY = [PERM.APP_EDIT, PERM.APP_PUBLISH];
const SKILL_ANY = [PERM.SKILL_EDIT, PERM.SKILL_PUBLISH];
const TOOL_ANY = [PERM.TOOL_EDIT, PERM.TOOL_CONTROL];
const KB_ANY = [PERM.KB_EDIT, PERM.KB_PUBLISH];
const SYSTEM_ANY = [PERM.SYSTEM_LLM, PERM.SYSTEM_SETTING];
const PERMISSION_ANY = [PERM.PERMISSION_USER, PERM.PERMISSION_ROLE];

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { public: true, title: "登录" },
    },
    {
      path: "/",
      component: () => import("@/layouts/MainLayout.vue"),
      meta: { requiresAuth: true },
      redirect: "/assistant",
      children: [
        {
          path: "assistant",
          name: "assistant",
          meta: {
            title: "智能助手",
            menu: { title: "智能助手", icon: "robot", order: 1 },
          },
          component: () => import("@/views/assistant/AssistantView.vue"),
        },
        {
          path: "app",
          name: "app",
          meta: {
            title: "应用工厂",
            menu: { title: "应用工厂", icon: "appstore", order: 2 },
            permissions: APP_ANY,
          },
          component: () => import("@/views/app/AppListView.vue"),
        },
        {
          path: "app/create",
          name: "app-create",
          meta: { title: "创建应用", permissions: [PERM.APP_EDIT] },
          component: () => import("@/views/app/AppFormView.vue"),
        },
        {
          path: "app/:id",
          name: "app-detail",
          meta: { title: "应用详情", permissions: APP_ANY },
          component: () => import("@/views/app/AppDetailView.vue"),
        },
        {
          path: "app/:id/edit",
          name: "app-edit",
          meta: { title: "编辑应用", permissions: [PERM.APP_EDIT] },
          component: () => import("@/views/app/AppFormView.vue"),
        },
        {
          path: "integration",
          name: "integration",
          meta: {
            title: "应用集成",
            menu: { title: "应用集成", icon: "api", order: 2.5 },
          },
          component: () => import("@/views/integration/IntegrationListView.vue"),
        },
        {
          path: "integration/create",
          name: "integration-create",
          meta: { title: "创建集成应用" },
          component: () => import("@/views/integration/IntegrationFormView.vue"),
        },
        {
          path: "integration/:id/edit",
          name: "integration-edit",
          meta: { title: "编辑集成应用" },
          component: () => import("@/views/integration/IntegrationFormView.vue"),
        },
        {
          path: "skill",
          name: "skill",
          meta: {
            title: "技能管理",
            menu: { title: "技能管理", icon: "cluster", order: 3 },
            permissions: SKILL_ANY,
          },
          component: () => import("@/views/skill/SkillListView.vue"),
        },
        {
          path: "skill/create",
          name: "skill-create",
          meta: { title: "创建技能", permissions: [PERM.SKILL_EDIT] },
          component: () => import("@/views/skill/SkillFormView.vue"),
        },
        {
          path: "skill/:id",
          name: "skill-detail",
          meta: { title: "技能详情", permissions: SKILL_ANY },
          component: () => import("@/views/skill/SkillDetailView.vue"),
        },
        {
          path: "skill/:id/edit",
          name: "skill-edit",
          meta: { title: "编辑技能", permissions: [PERM.SKILL_EDIT] },
          component: () => import("@/views/skill/SkillFormView.vue"),
        },
        {
          path: "tool",
          name: "tool",
          meta: {
            title: "工具管理",
            menu: { title: "工具管理", icon: "tool", order: 4 },
            permissions: TOOL_ANY,
          },
          component: () => import("@/views/tool/ToolListView.vue"),
        },
        {
          path: "tool/mcp-import",
          name: "tool-mcp-import",
          meta: { title: "从 MCP Server 导入", permissions: [PERM.TOOL_EDIT] },
          component: () => import("@/views/tool/McpImportView.vue"),
        },
        {
          path: "tool/api-tool",
          name: "tool-api-create",
          meta: { title: "集成外部 API 工具", permissions: [PERM.TOOL_EDIT] },
          component: () => import("@/views/tool/ApiToolView.vue"),
        },
        {
          path: "tool/api-tool/:id",
          name: "tool-api-edit",
          meta: { title: "编辑 API 工具", permissions: [PERM.TOOL_EDIT] },
          component: () => import("@/views/tool/ApiToolView.vue"),
        },
        {
          path: "knowledge",
          name: "knowledge",
          meta: {
            title: "知识库管理",
            menu: { title: "知识库管理", icon: "database", order: 5 },
            permissions: KB_ANY,
          },
          component: () => import("@/views/knowledge/KnowledgeView.vue"),
        },
        {
          path: "knowledge/:kbId/document/:docId/preview",
          name: "knowledge-doc-preview",
          meta: { title: "文档预览", permissions: KB_ANY },
          component: () => import("@/views/knowledge/KbDocumentPreviewView.vue"),
        },
        {
          path: "memory",
          name: "memory",
          meta: {
            title: "长期记忆",
            menu: { title: "长期记忆", icon: "bulb", order: 5.5 },
          },
          component: () => import("@/views/memory/MemoryView.vue"),
        },
        {
          path: "observability",
          name: "observability",
          meta: {
            title: "可观测性",
            menu: { title: "可观测性", icon: "eye", order: 6 },
          },
          component: () => import("@/views/observability/ObservabilityView.vue"),
        },
        {
          path: "observability/alert-rule/create",
          name: "alert-rule-create",
          meta: { title: "新建告警规则" },
          component: () => import("@/views/observability/AlertRuleFormView.vue"),
        },
        {
          path: "observability/alert-rule/:id/edit",
          name: "alert-rule-edit",
          meta: { title: "编辑告警规则" },
          component: () => import("@/views/observability/AlertRuleFormView.vue"),
        },
        {
          path: "setting",
          name: "setting",
          meta: {
            title: "系统配置",
            menu: { title: "系统配置", icon: "setting", order: 7 },
            permissions: SYSTEM_ANY,
          },
          component: () => import("@/views/setting/SettingView.vue"),
        },
        {
          path: "permission",
          name: "permission",
          meta: {
            title: "权限中心",
            menu: { title: "权限中心", icon: "safety", order: 8 },
            permissions: PERMISSION_ANY,
          },
          component: () => import("@/views/permission/PermissionCenterView.vue"),
        },
      ],
    },
  ],
});

router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore();
  if (!auth.initialized) {
    await auth.init();
  }
  if (to.meta.public) {
    if (auth.isLoggedIn && to.path === "/login") {
      next({ path: "/" });
      return;
    }
    next();
    return;
  }
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    next({ path: "/login", query: { redirect: to.fullPath } });
    return;
  }
  const required = (to.meta.permissions as string[] | undefined) ?? [];
  if (required.length && !auth.hasAnyPermission(required)) {
    next({ path: "/" });
    return;
  }
  next();
});

export default router;
