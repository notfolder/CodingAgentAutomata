import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import vuetify from './plugins/vuetify'

// Vue アプリケーション作成
const app = createApp(App)

// プラグイン登録
app.use(createPinia())  // 状態管理
app.use(router)          // ルーター
app.use(vuetify)         // UIフレームワーク

// #app にマウント
app.mount('#app')
