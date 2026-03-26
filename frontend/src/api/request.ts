import axios from "axios";
import { message } from "ant-design-vue";
import type { ApiResp } from "./types";

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "",
  timeout: 30_000,
});

request.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

request.interceptors.response.use(
  (res) => {
    const body = res.data as ApiResp<unknown>;
    if (body && typeof body.code === "number" && body.code !== 0) {
      message.error(body.msg || "请求失败");
      return Promise.reject(new Error(body.msg || "请求失败"));
    }
    return res;
  },
  (err) => {
    message.error(err?.message || "网络错误");
    return Promise.reject(err);
  },
);

export default request;
