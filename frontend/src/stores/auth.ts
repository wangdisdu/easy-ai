import { defineStore } from "pinia";
import { ref, computed } from "vue";
import * as authApi from "@/api/auth";
import type { UserResp } from "@/api/types";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<UserResp | null>(null);
  const initialized = ref(false);

  const isLoggedIn = computed(() => user.value !== null);

  async function login(account: string, passwd: string) {
    const { data } = await authApi.login(account, passwd);
    user.value = data.data.user;
    initialized.value = true;
  }

  async function logout() {
    try {
      await authApi.logout();
    } catch {
      /* ignore */
    }
    user.value = null;
  }

  async function loadProfile() {
    const { data } = await authApi.fetchMe();
    user.value = data.data;
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
      } finally {
        initialized.value = true;
        initPromise = null;
      }
    })();
    return initPromise;
  }

  return { user, initialized, isLoggedIn, login, logout, init };
});
