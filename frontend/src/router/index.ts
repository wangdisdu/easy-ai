import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { public: true },
    },
    {
      path: "/",
      component: () => import("@/layouts/MainLayout.vue"),
      meta: { requiresAuth: true },
      redirect: "/platform/user",
      children: [
        {
          path: "ai/workflow",
          name: "ai-workflow",
          meta: {
            breadcrumb: ["AI 应用", "智能体工作流"],
            menu: {
              groupKey: "ai-suite",
              groupTitle: "AI 应用",
              groupIcon: "appstore",
              itemTitle: "智能体工作流",
              itemIcon: "appstore",
            },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "ai/knowledge",
          name: "ai-knowledge",
          meta: {
            breadcrumb: ["AI 应用", "知识库管理"],
            menu: {
              groupKey: "ai-suite",
              groupTitle: "AI 应用",
              groupIcon: "appstore",
              itemTitle: "知识库管理",
              itemIcon: "team",
            },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "ai/text-to-sql",
          name: "ai-text-to-sql",
          meta: {
            breadcrumb: ["AI 应用", "TextToSQL"],
            menu: {
              groupKey: "ai-suite",
              groupTitle: "AI 应用",
              groupIcon: "appstore",
              itemTitle: "TextToSQL",
              itemIcon: "safety",
            },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "platform/user",
          name: "platform-user",
          meta: {
            breadcrumb: ["平台管理", "用户管理"],
            menu: {
              groupKey: "platform",
              groupTitle: "平台管理",
              groupIcon: "appstore",
              itemTitle: "用户管理",
              itemIcon: "user",
            },
          },
          component: () => import("@/views/platform/UserManageView.vue"),
        },
        {
          path: "platform/user-group",
          name: "platform-user-group",
          meta: {
            breadcrumb: ["平台管理", "用户组管理"],
            menu: {
              groupKey: "platform",
              groupTitle: "平台管理",
              groupIcon: "appstore",
              itemTitle: "用户组管理",
              itemIcon: "team",
            },
          },
          component: () => import("@/views/platform/UserGroupManageView.vue"),
        },
        {
          path: "platform/role",
          name: "platform-role",
          meta: {
            breadcrumb: ["平台管理", "角色管理"],
            menu: {
              groupKey: "platform",
              groupTitle: "平台管理",
              groupIcon: "appstore",
              itemTitle: "角色管理",
              itemIcon: "safety",
            },
          },
          component: () => import("@/views/platform/RoleManageView.vue"),
        },
      ],
    },
  ],
});

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore();
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
  next();
});

export default router;
