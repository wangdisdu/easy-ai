import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

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
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "app",
          name: "app",
          meta: {
            title: "应用工厂",
            menu: { title: "应用工厂", icon: "appstore", order: 2 },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "skills",
          name: "skills",
          meta: {
            title: "技能管理",
            menu: { title: "技能管理", icon: "cluster", order: 3 },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "tools",
          name: "tools",
          meta: {
            title: "工具管理",
            menu: { title: "工具管理", icon: "tool", order: 4 },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "knowledge",
          name: "knowledge",
          meta: {
            title: "知识库管理",
            menu: { title: "知识库管理", icon: "database", order: 5 },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "observability",
          name: "observability",
          meta: {
            title: "可观测性",
            menu: { title: "可观测性", icon: "eye", order: 6 },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "setting",
          name: "setting",
          meta: {
            title: "系统配置",
            menu: { title: "系统配置", icon: "setting", order: 7 },
          },
          component: () => import("@/views/MockFeatureView.vue"),
        },
        {
          path: "permission",
          name: "permission",
          meta: {
            title: "权限中心",
            menu: { title: "权限中心", icon: "safety", order: 8 },
          },
          component: () => import("@/views/permission/PermissionCenterView.vue"),
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
