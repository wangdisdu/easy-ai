import { defineStore } from "pinia";
import { ref, computed } from "vue";
import * as authApi from "@/api/auth";
import type { UserResp } from "@/api/types";

const TOKEN_KEY = "access_token";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY));
  const user = ref<UserResp | null>(null);

  const isLoggedIn = computed(() => Boolean(token.value));

  function setToken(t: string | null) {
    token.value = t;
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  }

  async function login(account: string, passwd: string) {
    const { data } = await authApi.login(account, passwd);
    setToken(data.data.access_token);
    user.value = data.data.user;
  }

  function logout() {
    setToken(null);
    user.value = null;
  }

  async function loadProfile() {
    if (!token.value) return;
    const { data } = await authApi.fetchMe();
    user.value = data.data;
  }

  return { token, user, isLoggedIn, login, logout, loadProfile };
});
