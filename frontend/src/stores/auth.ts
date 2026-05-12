import { defineStore } from "pinia";
import { ref, computed } from "vue";
import * as authApi from "@/api/auth";
import { listRole } from "@/api/role";
import type { UserResp } from "@/api/types";

const PERMISSION_WILDCARD = "*";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<UserResp | null>(null);
  const permissions = ref<string[]>([]);
  const initialized = ref(false);

  const isLoggedIn = computed(() => user.value !== null);
  const isSuperAdmin = computed(() => permissions.value.includes(PERMISSION_WILDCARD));

  function hasPermission(code: string): boolean {
    if (!permissions.value.length) return false;
    if (permissions.value.includes(PERMISSION_WILDCARD)) return true;
    return permissions.value.includes(code);
  }

  function hasAnyPermission(codes: string[]): boolean {
    if (!codes.length) return true;
    return codes.some((code) => hasPermission(code));
  }

  async function loadPermissions() {
    if (!user.value?.roles?.length) {
      permissions.value = [];
      return;
    }
    try {
      const { data } = await listRole();
      const myRoleIds = new Set(user.value.roles.map((r) => r.id));
      const codes = new Set<string>();
      for (const role of data.data) {
        if (!myRoleIds.has(role.id)) continue;
        for (const code of role.permissions ?? []) {
          codes.add(code);
        }
      }
      permissions.value = Array.from(codes);
    } catch {
      permissions.value = [];
    }
  }

  async function login(account: string, passwd: string) {
    const { data } = await authApi.login(account, passwd);
    user.value = data.data.user;
    await loadPermissions();
    initialized.value = true;
  }

  async function logout() {
    try {
      await authApi.logout();
    } catch {
      /* ignore */
    }
    user.value = null;
    permissions.value = [];
  }

  async function loadProfile() {
    const { data } = await authApi.fetchMe();
    user.value = data.data;
    await loadPermissions();
  }

  let initPromise: Promise<void> | null = null;
  function init() {
    if (initialized.value) return Promise.resolve();
    if (initPromise) return initPromise;
    initPromise = (async () => {
      try {
        await loadProfile();
      } catch {
        user.value = null;
        permissions.value = [];
      } finally {
        initialized.value = true;
        initPromise = null;
      }
    })();
    return initPromise;
  }

  return {
    user,
    permissions,
    initialized,
    isLoggedIn,
    isSuperAdmin,
    hasPermission,
    hasAnyPermission,
    login,
    logout,
    init,
  };
});
