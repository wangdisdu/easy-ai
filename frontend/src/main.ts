import { createApp } from "vue";
import { createPinia } from "pinia";
import Antd from "ant-design-vue";
import "ant-design-vue/dist/reset.css";
import App from "./App.vue";
import router from "./router";
import "./assets/base.css";
import "./styles/tokens.css";
import { useThemeStore } from "./stores/theme";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia);

// 在 mount 之前应用 data-theme，避免首屏从亮色闪到暗色。
useThemeStore(pinia).init();

app.use(router);
app.use(Antd);
app.mount("#app");
