<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()

// ナビゲーションバーの表示制御
const showNav = computed(() => auth.isAuthenticated)
const profilePath = computed(() => `/users/${auth.currentUsername}`)

// ログアウト処理
function handleLogout(): void {
  auth.logout()
  void router.push('/login')
}
</script>

<template>
  <v-app>
    <!-- ナビゲーションバー（認証済みのみ表示） -->
    <v-app-bar v-if="showNav" color="primary" elevation="2">
      <v-app-bar-title>CodingAgentAutomata</v-app-bar-title>
      <v-spacer />

      <!-- ユーザー一覧（admin のみ） -->
      <v-btn v-if="auth.isAdmin" to="/users" variant="text">
        <v-icon left>mdi-account-group</v-icon>
        ユーザー一覧
      </v-btn>

      <!-- 自分の設定（全ユーザー） -->
      <v-btn :to="profilePath" variant="text">
        <v-icon left>mdi-account-cog</v-icon>
        自分の設定
      </v-btn>

      <!-- タスク実行履歴 -->
      <v-btn to="/tasks" variant="text">
        <v-icon left>mdi-clipboard-list</v-icon>
        タスク履歴
      </v-btn>

      <!-- Group Webhook管理（全ユーザー） -->
      <v-btn to="/webhooks" variant="text">
        <v-icon left>mdi-webhook</v-icon>
        Webhook管理
      </v-btn>

      <!-- システム設定（admin のみ） -->
      <v-btn v-if="auth.isAdmin" to="/settings" variant="text">
        <v-icon left>mdi-cog</v-icon>
        システム設定
      </v-btn>

      <!-- ログアウト -->
      <v-btn variant="text" @click="handleLogout">
        <v-icon left>mdi-logout</v-icon>
        ログアウト
      </v-btn>
    </v-app-bar>

    <!-- メインコンテンツ -->
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
