<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getUsers, type UserResponse } from '../api/client'

const router = useRouter()

// テーブルのヘッダー定義
const headers = [
  { title: 'ユーザー名', key: 'username', sortable: true },
  { title: 'メールアドレス', key: 'email', sortable: true },
  { title: 'ロール', key: 'role', sortable: true },
  { title: 'ステータス', key: 'is_active', sortable: true },
  { title: '登録日時', key: 'created_at', sortable: true },
]

// 状態管理
const users = ref<UserResponse[]>([])
const totalCount = ref(0)
const currentPage = ref(1)
const perPage = ref(20)
const searchText = ref('')
const loading = ref(false)
const errorMessage = ref('')

// ページ数計算
const pageCount = ref(0)

/**
 * ユーザー一覧を取得する
 */
async function fetchUsers(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await getUsers(searchText.value || undefined, currentPage.value)
    users.value = data.items
    totalCount.value = data.total
    perPage.value = data.per_page
    pageCount.value = Math.ceil(data.total / data.per_page)
  } catch {
    errorMessage.value = 'ユーザー一覧の取得に失敗しました。'
  } finally {
    loading.value = false
  }
}

/**
 * 検索実行（ページを1に戻してから取得）
 */
async function handleSearch(): Promise<void> {
  currentPage.value = 1
  await fetchUsers()
}

/**
 * ページ変更時の処理
 */
async function handlePageChange(page: number): Promise<void> {
  currentPage.value = page
  await fetchUsers()
}

/**
 * 行クリックでユーザー詳細画面へ遷移
 */
async function handleRowClick(_event: Event, row: { item: UserResponse }): Promise<void> {
  await router.push(`/users/${row.item.username}`)
}

/**
 * 日時文字列をフォーマットする
 */
function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('ja-JP')
}

// コンポーネントマウント時にユーザー一覧を取得
onMounted(() => {
  void fetchUsers()
})
</script>

<template>
  <!-- SC-02: ユーザー一覧画面（admin のみ） -->
  <v-container fluid class="pa-6">
    <!-- ページヘッダー -->
    <v-row class="mb-4" align="center">
      <v-col>
        <h1 class="text-h5">
          <v-icon class="mr-2">mdi-account-group</v-icon>
          ユーザー一覧
        </h1>
      </v-col>
      <v-col cols="auto">
        <!-- 新規作成ボタン -->
        <v-btn color="primary" prepend-icon="mdi-plus" to="/users/new">
          新規ユーザー作成
        </v-btn>
      </v-col>
    </v-row>

    <!-- エラーアラート -->
    <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" closable>
      {{ errorMessage }}
    </v-alert>

    <!-- 検索エリア -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text>
        <v-row align="center">
          <v-col cols="12" md="6">
            <v-text-field
              v-model="searchText"
              label="ユーザー名で検索（前方一致）"
              prepend-inner-icon="mdi-magnify"
              variant="outlined"
              density="compact"
              hide-details
              clearable
              @keyup.enter="handleSearch"
              @click:clear="handleSearch"
            />
          </v-col>
          <v-col cols="auto">
            <v-btn color="primary" variant="tonal" @click="handleSearch">検索</v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- ユーザー一覧テーブル -->
    <v-card variant="outlined">
      <v-data-table
        :headers="headers"
        :items="users"
        :loading="loading"
        loading-text="読み込み中..."
        no-data-text="ユーザーが見つかりません"
        hide-default-footer
        @click:row="handleRowClick"
        style="cursor: pointer"
      >
        <!-- ロール列のカスタム表示 -->
        <template #item.role="{ item }">
          <v-chip
            :color="item.role === 'admin' ? 'error' : 'primary'"
            size="small"
            variant="tonal"
          >
            {{ item.role === 'admin' ? '管理者' : '一般ユーザー' }}
          </v-chip>
        </template>

        <!-- ステータス列のカスタム表示 -->
        <template #item.is_active="{ item }">
          <v-chip
            :color="item.is_active ? 'success' : 'default'"
            size="small"
            variant="tonal"
          >
            {{ item.is_active ? '有効' : '無効' }}
          </v-chip>
        </template>

        <!-- 登録日時列のカスタム表示 -->
        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>
      </v-data-table>

      <!-- ページネーション -->
      <v-divider />
      <v-card-text class="d-flex justify-space-between align-center">
        <span class="text-caption text-medium-emphasis">全 {{ totalCount }} 件</span>
        <v-pagination
          v-if="pageCount > 1"
          v-model="currentPage"
          :length="pageCount"
          rounded="circle"
          @update:model-value="handlePageChange"
        />
      </v-card-text>
    </v-card>
  </v-container>
</template>
