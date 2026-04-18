<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getSettings,
  updateSettings,
  getAdapters,
  createAdapter,
  updateAdapter,
  deleteAdapter,
  type CLIAdapterResponse,
  type CLIAdapterCreateData,
  type SystemSettingsResponse,
} from '../api/client'
import axios from 'axios'

// アクティブタブ
const activeTab = ref('f3')

// 状態管理
const loading = ref(false)
const saveLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

// ============================================================
// システム設定
// ============================================================
const settings = ref<SystemSettingsResponse>({
  f3_prompt_template: null,
  f4_prompt_template: null,
  system_mcp_config: null,
})

// テンプレートの編集値
const f3Template = ref('')
const f4Template = ref('')
const systemMcpConfig = ref('')

/**
 * システム設定を取得する
 */
async function fetchSettings(): Promise<void> {
  loading.value = true
  try {
    settings.value = await getSettings()
    f3Template.value = settings.value.f3_prompt_template ?? ''
    f4Template.value = settings.value.f4_prompt_template ?? ''
    systemMcpConfig.value = settings.value.system_mcp_config
      ? JSON.stringify(settings.value.system_mcp_config, null, 2)
      : ''
  } catch {
    errorMessage.value = 'システム設定の取得に失敗しました。'
  } finally {
    loading.value = false
  }
}

/**
 * 現在表示中のタブに応じて保存処理を実行する
 */
async function handleSave(): Promise<void> {
  saveLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    if (activeTab.value === 'f3' || activeTab.value === 'f4') {
      // F-3/F-4テンプレートの保存
      await updateSettings({
        f3_prompt_template: f3Template.value || null,
        f4_prompt_template: f4Template.value || null,
      })
    } else if (activeTab.value === 'mcp') {
      // システムMCP設定の保存（JSON検証）
      let parsedConfig: unknown = null
      if (systemMcpConfig.value.trim()) {
        try {
          parsedConfig = JSON.parse(systemMcpConfig.value)
        } catch {
          errorMessage.value = 'システムMCP設定のJSON形式が不正です。'
          saveLoading.value = false
          return
        }
      }
      await updateSettings({ system_mcp_config: parsedConfig })
    }
    successMessage.value = '設定を保存しました。'
  } catch {
    errorMessage.value = '設定の保存に失敗しました。'
  } finally {
    saveLoading.value = false
  }
}

// ============================================================
// CLIアダプタ管理
// ============================================================
const adapters = ref<CLIAdapterResponse[]>([])
const adapterLoading = ref(false)

// アダプタ追加・編集ダイアログ
const adapterDialog = ref(false)
const adapterDialogMode = ref<'create' | 'edit'>('create')
const editingAdapterId = ref('')

// アダプタフォーム
const adapterForm = ref({
  cli_id: '',
  container_image: '',
  start_command_template: '',
  env_mappings_str: '{}',
  config_content_env: '',
  is_builtin: false,
})
const adapterFormRef = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)

// アダプタ削除確認ダイアログ
const deleteAdapterDialog = ref(false)
const deletingAdapterId = ref('')

// アダプタテーブルのヘッダー
const adapterHeaders = [
  { title: 'CLI ID', key: 'cli_id', sortable: true },
  { title: 'コンテナイメージ', key: 'container_image', sortable: true },
  { title: '組み込み', key: 'is_builtin', sortable: true },
  { title: '登録日時', key: 'created_at', sortable: true },
  { title: '操作', key: 'actions', sortable: false },
]

// バリデーションルール
const adapterRules = {
  required: (v: string) => !!v || 'このフィールドは必須です',
  json: (v: string) => {
    try {
      JSON.parse(v)
      return true
    } catch {
      return '有効なJSON形式で入力してください'
    }
  },
}

/**
 * CLIアダプタ一覧を取得する
 */
async function fetchAdapters(): Promise<void> {
  adapterLoading.value = true
  try {
    adapters.value = await getAdapters()
  } catch {
    errorMessage.value = 'CLIアダプタ一覧の取得に失敗しました。'
  } finally {
    adapterLoading.value = false
  }
}

/**
 * アダプタ追加ダイアログを開く
 */
function openCreateAdapterDialog(): void {
  adapterDialogMode.value = 'create'
  adapterForm.value = {
    cli_id: '',
    container_image: '',
    start_command_template: '',
    env_mappings_str: '{}',
    config_content_env: '',
    is_builtin: false,
  }
  adapterDialog.value = true
}

/**
 * アダプタ編集ダイアログを開く
 */
function openEditAdapterDialog(adapter: CLIAdapterResponse): void {
  adapterDialogMode.value = 'edit'
  editingAdapterId.value = adapter.cli_id
  adapterForm.value = {
    cli_id: adapter.cli_id,
    container_image: adapter.container_image,
    start_command_template: adapter.start_command_template,
    env_mappings_str: JSON.stringify(adapter.env_mappings, null, 2),
    config_content_env: adapter.config_content_env ?? '',
    is_builtin: adapter.is_builtin,
  }
  adapterDialog.value = true
}

/**
 * アダプタの保存処理（追加または更新）
 */
async function handleSaveAdapter(): Promise<void> {
  if (!adapterFormRef.value) return
  const { valid } = await adapterFormRef.value.validate()
  if (!valid) return

  adapterLoading.value = true
  errorMessage.value = ''

  try {
    const envMappings = JSON.parse(adapterForm.value.env_mappings_str) as Record<string, unknown>

    if (adapterDialogMode.value === 'create') {
      const createData: CLIAdapterCreateData = {
        cli_id: adapterForm.value.cli_id,
        container_image: adapterForm.value.container_image,
        start_command_template: adapterForm.value.start_command_template,
        env_mappings: envMappings,
        is_builtin: adapterForm.value.is_builtin,
      }
      if (adapterForm.value.config_content_env) {
        createData.config_content_env = adapterForm.value.config_content_env
      }
      await createAdapter(createData)
    } else {
      await updateAdapter(editingAdapterId.value, {
        container_image: adapterForm.value.container_image,
        start_command_template: adapterForm.value.start_command_template,
        env_mappings: envMappings,
        config_content_env: adapterForm.value.config_content_env || undefined,
      })
    }

    successMessage.value =
      adapterDialogMode.value === 'create'
        ? 'CLIアダプタを作成しました。'
        : 'CLIアダプタを更新しました。'
    adapterDialog.value = false
    await fetchAdapters()
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      errorMessage.value = 'このCLI IDは既に使用されています。'
    } else {
      errorMessage.value = 'CLIアダプタの保存に失敗しました。'
    }
  } finally {
    adapterLoading.value = false
  }
}

/**
 * アダプタ削除確認ダイアログを開く
 */
function openDeleteAdapterDialog(adapterId: string): void {
  deletingAdapterId.value = adapterId
  deleteAdapterDialog.value = true
}

/**
 * アダプタ削除処理
 */
async function handleDeleteAdapter(): Promise<void> {
  adapterLoading.value = true
  errorMessage.value = ''

  try {
    await deleteAdapter(deletingAdapterId.value)
    successMessage.value = 'CLIアダプタを削除しました。'
    deleteAdapterDialog.value = false
    await fetchAdapters()
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 400) {
      errorMessage.value =
        'このアダプタは組み込みアダプタまたはユーザーが使用中のため削除できません。'
    } else {
      errorMessage.value = 'CLIアダプタの削除に失敗しました。'
    }
    deleteAdapterDialog.value = false
  } finally {
    adapterLoading.value = false
  }
}

/**
 * 日時文字列をフォーマットする
 */
function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('ja-JP')
}

// コンポーネントマウント時にデータ取得
onMounted(async () => {
  await Promise.all([fetchSettings(), fetchAdapters()])
})
</script>

<template>
  <!-- SC-07: システム設定画面（admin のみ） -->
  <v-container fluid class="pa-6">
    <!-- ページヘッダー -->
    <v-row class="mb-4" align="center">
      <v-col>
        <h1 class="text-h5">
          <v-icon class="mr-2">mdi-cog</v-icon>
          システム設定
        </h1>
      </v-col>
    </v-row>

    <!-- エラーアラート -->
    <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" closable @click:close="errorMessage = ''">
      {{ errorMessage }}
    </v-alert>

    <!-- 成功フラッシュメッセージ -->
    <v-alert
      v-if="successMessage"
      type="success"
      variant="tonal"
      class="mb-4"
      closable
      @click:close="successMessage = ''"
    >
      {{ successMessage }}
    </v-alert>

    <!-- タブナビゲーション -->
    <v-card variant="outlined">
      <v-tabs v-model="activeTab" color="primary">
        <v-tab value="f3">F-3 テンプレート</v-tab>
        <v-tab value="f4">F-4 テンプレート</v-tab>
        <v-tab value="adapters">CLI アダプタ</v-tab>
        <v-tab value="mcp">MCP 設定</v-tab>
      </v-tabs>

      <v-divider />

      <v-window v-model="activeTab">
        <!-- F-3 テンプレート設定タブ -->
        <v-window-item value="f3">
          <v-card-text class="pa-6">
            <v-row>
              <v-col cols="12">
                <h2 class="text-subtitle-1 font-weight-bold mb-2">F-3 プロンプトテンプレート</h2>
                <p class="text-body-2 text-medium-emphasis mb-3">
                  Issue を MR に変換する際に使用するプロンプトテンプレートを設定します。
                </p>
                <!-- 使用可能な変数のヘルプテキスト -->
                <v-alert type="info" variant="tonal" density="compact" class="mb-3">
                  <strong>使用可能な変数:</strong>
                  <code>{issue_title}</code>（Issueタイトル）、
                  <code>{issue_description}</code>（Issue説明）、
                  <code>{issue_comments}</code>（Issueコメント一覧）、
                  <code>{repository_url}</code>（リポジトリURL）、
                  <code>{branch_name}</code>（ブランチ名）
                </v-alert>
                <v-textarea
                  v-model="f3Template"
                  variant="outlined"
                  rows="16"
                  placeholder="F-3プロンプトテンプレートを入力してください..."
                  :loading="loading"
                  font-family="monospace"
                />
              </v-col>
            </v-row>
            <v-btn
              color="primary"
              :loading="saveLoading"
              prepend-icon="mdi-content-save"
              @click="handleSave"
            >
              保存する
            </v-btn>
          </v-card-text>
        </v-window-item>

        <!-- F-4 テンプレート設定タブ -->
        <v-window-item value="f4">
          <v-card-text class="pa-6">
            <v-row>
              <v-col cols="12">
                <h2 class="text-subtitle-1 font-weight-bold mb-2">
                  F-4 プロンプトテンプレート（システムデフォルト）
                </h2>
                <p class="text-body-2 text-medium-emphasis mb-3">
                  MR 処理時に使用するシステムデフォルトのプロンプトテンプレートを設定します。
                  ユーザー個別テンプレートが設定されている場合はそちらが優先されます。
                </p>
                <!-- 使用可能な変数のヘルプテキスト -->
                <v-alert type="info" variant="tonal" density="compact" class="mb-3">
                  <strong>使用可能な変数:</strong>
                  <code>{mr_description}</code>（MRの説明）、
                  <code>{mr_comments}</code>（MRのコメント一覧）、
                  <code>{branch_name}</code>（ブランチ名）、
                  <code>{repository_url}</code>（リポジトリURL）
                </v-alert>
                <v-textarea
                  v-model="f4Template"
                  variant="outlined"
                  rows="16"
                  placeholder="F-4プロンプトテンプレートを入力してください..."
                  :loading="loading"
                  font-family="monospace"
                />
              </v-col>
            </v-row>
            <v-btn
              color="primary"
              :loading="saveLoading"
              prepend-icon="mdi-content-save"
              @click="handleSave"
            >
              保存する
            </v-btn>
          </v-card-text>
        </v-window-item>

        <!-- CLIアダプタ管理タブ -->
        <v-window-item value="adapters">
          <v-card-text class="pa-6">
            <v-row class="mb-4" align="center">
              <v-col>
                <h2 class="text-subtitle-1 font-weight-bold">CLI アダプタ一覧</h2>
              </v-col>
              <v-col cols="auto">
                <v-btn
                  color="primary"
                  prepend-icon="mdi-plus"
                  @click="openCreateAdapterDialog"
                >
                  追加
                </v-btn>
              </v-col>
            </v-row>

            <v-data-table
              :headers="adapterHeaders"
              :items="adapters"
              :loading="adapterLoading"
              loading-text="読み込み中..."
              no-data-text="CLIアダプタが登録されていません"
              hide-default-footer
            >
              <!-- 組み込みフラグのカスタム表示 -->
              <template #item.is_builtin="{ item }">
                <v-chip v-if="item.is_builtin" color="primary" size="small" variant="tonal">
                  組み込み
                </v-chip>
                <v-chip v-else color="default" size="small" variant="tonal">
                  カスタム
                </v-chip>
              </template>

              <!-- 登録日時のカスタム表示 -->
              <template #item.created_at="{ item }">
                {{ formatDate(item.created_at) }}
              </template>

              <!-- 操作ボタン -->
              <template #item.actions="{ item }">
                <v-btn
                  size="small"
                  variant="text"
                  icon="mdi-pencil"
                  @click="openEditAdapterDialog(item)"
                />
                <v-btn
                  size="small"
                  variant="text"
                  icon="mdi-delete"
                  color="error"
                  :disabled="item.is_builtin"
                  @click="openDeleteAdapterDialog(item.cli_id)"
                />
              </template>
            </v-data-table>
          </v-card-text>
        </v-window-item>

        <!-- システム MCP 設定タブ -->
        <v-window-item value="mcp">
          <v-card-text class="pa-6">
            <v-row>
              <v-col cols="12">
                <h2 class="text-subtitle-1 font-weight-bold mb-2">システム MCP 設定</h2>
                <p class="text-body-2 text-medium-emphasis mb-3">
                  全ユーザーに適用するシステムデフォルトの MCP 設定を JSON 形式で設定します。
                  ユーザーが「システムMCP設定を使用する」を有効にしている場合に適用されます。
                </p>
                <v-textarea
                  v-model="systemMcpConfig"
                  variant="outlined"
                  rows="16"
                  placeholder='{"mcpServers": {}}'
                  :loading="loading"
                  font-family="monospace"
                  hint="JSON形式で入力してください"
                  persistent-hint
                />
              </v-col>
            </v-row>
            <v-btn
              color="primary"
              class="mt-4"
              :loading="saveLoading"
              prepend-icon="mdi-content-save"
              @click="handleSave"
            >
              保存する
            </v-btn>
          </v-card-text>
        </v-window-item>
      </v-window>
    </v-card>

    <!-- CLIアダプタ追加・編集ダイアログ -->
    <v-dialog v-model="adapterDialog" max-width="700">
      <v-card>
        <v-card-title class="text-h6 pa-6">
          {{ adapterDialogMode === 'create' ? 'CLIアダプタ追加' : 'CLIアダプタ編集' }}
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-6">
          <v-form ref="adapterFormRef">
            <v-row>
              <!-- CLI ID（作成時のみ） -->
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="adapterForm.cli_id"
                  label="CLI ID *"
                  variant="outlined"
                  :rules="[adapterRules.required]"
                  :readonly="adapterDialogMode === 'edit'"
                  hint="例: claude, opencode"
                  persistent-hint
                />
              </v-col>

              <!-- コンテナイメージ -->
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="adapterForm.container_image"
                  label="コンテナイメージ *"
                  variant="outlined"
                  :rules="[adapterRules.required]"
                  hint="例: coding-agent-cli-exec-claude:latest"
                  persistent-hint
                />
              </v-col>

              <!-- 起動コマンドテンプレート -->
              <v-col cols="12">
                <v-text-field
                  v-model="adapterForm.start_command_template"
                  label="起動コマンドテンプレート *"
                  variant="outlined"
                  :rules="[adapterRules.required]"
                />
              </v-col>

              <!-- 環境変数マッピング（JSON） -->
              <v-col cols="12">
                <v-textarea
                  v-model="adapterForm.env_mappings_str"
                  label="環境変数マッピング（JSON） *"
                  variant="outlined"
                  rows="5"
                  :rules="[adapterRules.required, adapterRules.json]"
                  font-family="monospace"
                />
              </v-col>

              <!-- 設定内容環境変数名 -->
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="adapterForm.config_content_env"
                  label="設定内容環境変数名（省略可）"
                  variant="outlined"
                  hint="設定をJSON環境変数で渡す場合の変数名"
                  persistent-hint
                />
              </v-col>

              <!-- 組み込みフラグ（作成時のみ） -->
              <v-col v-if="adapterDialogMode === 'create'" cols="12" md="6">
                <v-switch
                  v-model="adapterForm.is_builtin"
                  label="組み込みアダプタ"
                  color="primary"
                  inset
                />
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="adapterDialog = false">キャンセル</v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="adapterLoading"
            @click="handleSaveAdapter"
          >
            {{ adapterDialogMode === 'create' ? '追加する' : '更新する' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- CLIアダプタ削除確認ダイアログ -->
    <v-dialog v-model="deleteAdapterDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">CLIアダプタ削除の確認</v-card-title>
        <v-card-text>
          CLIアダプタ「{{ deletingAdapterId }}」を削除しますか？この操作は取り消せません。
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteAdapterDialog = false">キャンセル</v-btn>
          <v-btn
            color="error"
            variant="tonal"
            :loading="adapterLoading"
            @click="handleDeleteAdapter"
          >
            削除する
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
