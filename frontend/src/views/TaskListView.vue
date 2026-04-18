<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getTasks, type TaskResponse } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

// テーブルのヘッダー定義
const headers = [
  { title: 'タスクUUID', key: 'task_uuid', sortable: false },
  { title: '種別', key: 'task_type', sortable: true },
  { title: 'ユーザー名', key: 'username', sortable: true },
  { title: 'プロジェクトID', key: 'gitlab_project_id', sortable: true },
  { title: 'IID', key: 'source_iid', sortable: true },
  { title: 'ステータス', key: 'status', sortable: true },
  { title: 'CLI', key: 'cli_type', sortable: true },
  { title: 'モデル', key: 'model', sortable: true },
  { title: '作成日時', key: 'created_at', sortable: true },
  { title: '完了日時', key: 'completed_at', sortable: true },
]

// フィルタ状態
const filterStatus = ref<string | null>(null)
const filterUsername = ref<string>('')
const filterTaskType = ref<string | null>(null)
const currentPage = ref(1)

// データ状態
const tasks = ref<TaskResponse[]>([])
const totalCount = ref(0)
const perPage = ref(20)
const loading = ref(false)
const errorMessage = ref('')

// ページ数計算
const pageCount = computed(() => Math.ceil(totalCount.value / perPage.value))

// ステータス選択肢
const statusOptions = [
  { title: '全て', value: null },
  { title: '保留中', value: 'pending' },
  { title: '実行中', value: 'running' },
  { title: '完了', value: 'completed' },
  { title: '失敗', value: 'failed' },
]

// タスク種別選択肢
const taskTypeOptions = [
  { title: '全て', value: null },
  { title: 'Issue', value: 'issue' },
  { title: 'Merge Request', value: 'merge_request' },
]

// 一般ユーザーはユーザー名フィルタが自分固定
const usernameFilterReadonly = computed(() => !auth.isAdmin)

/**
 * タスク一覧を取得する
 */
async function fetchTasks(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const params: {
      username?: string
      status?: string
      task_type?: string
      page?: number
    } = { page: currentPage.value }

    // admin はフィルタ入力を使用、一般ユーザーは自分固定
    if (auth.isAdmin) {
      if (filterUsername.value) params.username = filterUsername.value
    } else {
      params.username = auth.currentUsername
    }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterTaskType.value) params.task_type = filterTaskType.value

    const data = await getTasks(params)
    tasks.value = data.items
    totalCount.value = data.total
    perPage.value = data.per_page
  } catch {
    errorMessage.value = 'タスク一覧の取得に失敗しました。'
  } finally {
    loading.value = false
  }
}

/**
 * フィルタ変更時の処理（ページを1に戻してから取得）
 */
async function handleFilterChange(): Promise<void> {
  currentPage.value = 1
  await fetchTasks()
}

/**
 * ページ変更時の処理
 */
async function handlePageChange(page: number): Promise<void> {
  currentPage.value = page
  await fetchTasks()
}

/**
 * ステータスに対応する色を返す
 */
function statusColor(status: string): string {
  const colorMap: Record<string, string> = {
    pending: 'warning',
    running: 'info',
    completed: 'success',
    failed: 'error',
  }
  return colorMap[status] ?? 'default'
}

/**
 * ステータスの日本語表示
 */
function statusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    pending: '保留中',
    running: '実行中',
    completed: '完了',
    failed: '失敗',
  }
  return labelMap[status] ?? status
}

/**
 * タスク種別の日本語表示
 */
function taskTypeLabel(taskType: string): string {
  return taskType === 'issue' ? 'Issue' : 'MR'
}

/**
 * 日時文字列をフォーマットする
 */
function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('ja-JP')
}

/**
 * UUIDの短縮表示（先頭8文字）
 */
function shortUuid(uuid: string): string {
  return uuid.substring(0, 8) + '...'
}

// コンポーネントマウント時にデータ取得
onMounted(() => {
  // 一般ユーザーはフィルタに自分のユーザー名をセット
  if (!auth.isAdmin) {
    filterUsername.value = auth.currentUsername
  }
  void fetchTasks()
})
</script>

<template>
  <!-- SC-06: タスク実行履歴画面 -->
  <v-container fluid class="pa-6">
    <!-- ページヘッダー -->
    <v-row class="mb-4" align="center">
      <v-col>
        <h1 class="text-h5">
          <v-icon class="mr-2">mdi-clipboard-list</v-icon>
          タスク実行履歴
        </h1>
      </v-col>
      <v-col cols="auto">
        <v-btn
          variant="tonal"
          prepend-icon="mdi-refresh"
          :loading="loading"
          @click="fetchTasks"
        >
          更新
        </v-btn>
      </v-col>
    </v-row>

    <!-- エラーアラート -->
    <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" closable>
      {{ errorMessage }}
    </v-alert>

    <!-- フィルタエリア -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text>
        <v-row align="center">
          <!-- ステータスフィルタ -->
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="filterStatus"
              label="ステータス"
              :items="statusOptions"
              variant="outlined"
              density="compact"
              hide-details
              clearable
              @update:model-value="handleFilterChange"
            />
          </v-col>

          <!-- ユーザー名フィルタ（admin: 入力可 / user: 自分固定） -->
          <v-col cols="12" sm="4" md="3">
            <v-text-field
              v-model="filterUsername"
              label="ユーザー名"
              variant="outlined"
              density="compact"
              hide-details
              :readonly="usernameFilterReadonly"
              clearable
              @keyup.enter="handleFilterChange"
              @click:clear="handleFilterChange"
            />
          </v-col>

          <!-- タスク種別フィルタ -->
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="filterTaskType"
              label="タスク種別"
              :items="taskTypeOptions"
              variant="outlined"
              density="compact"
              hide-details
              clearable
              @update:model-value="handleFilterChange"
            />
          </v-col>

          <v-col cols="auto">
            <v-btn color="primary" variant="tonal" @click="handleFilterChange">絞り込み</v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- タスク一覧テーブル -->
    <v-card variant="outlined">
      <v-data-table
        :headers="headers"
        :items="tasks"
        :loading="loading"
        loading-text="読み込み中..."
        no-data-text="タスクが見つかりません"
        hide-default-footer
        density="compact"
      >
        <!-- タスクUUID（短縮表示） -->
        <template #item.task_uuid="{ item }">
          <v-tooltip :text="item.task_uuid" location="top">
            <template #activator="{ props }">
              <code v-bind="props">{{ shortUuid(item.task_uuid) }}</code>
            </template>
          </v-tooltip>
        </template>

        <!-- 種別のカスタム表示 -->
        <template #item.task_type="{ item }">
          <v-chip size="small" variant="tonal" color="primary">
            {{ taskTypeLabel(item.task_type) }}
          </v-chip>
        </template>

        <!-- ステータスのカスタム表示 -->
        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
            {{ statusLabel(item.status) }}
          </v-chip>
        </template>

        <!-- 作成日時のカスタム表示 -->
        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>

        <!-- 完了日時のカスタム表示 -->
        <template #item.completed_at="{ item }">
          {{ formatDate(item.completed_at) }}
        </template>

        <!-- CLI のカスタム表示 -->
        <template #item.cli_type="{ item }">
          {{ item.cli_type ?? '-' }}
        </template>

        <!-- モデルのカスタム表示 -->
        <template #item.model="{ item }">
          {{ item.model ?? '-' }}
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
