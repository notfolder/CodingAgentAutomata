import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// 各ビューコンポーネントを遅延インポート
const LoginView = () => import('../views/LoginView.vue')
const UserListView = () => import('../views/UserListView.vue')
const UserCreateView = () => import('../views/UserCreateView.vue')
const UserDetailView = () => import('../views/UserDetailView.vue')
const UserEditView = () => import('../views/UserEditView.vue')
const TaskListView = () => import('../views/TaskListView.vue')
const SettingsView = () => import('../views/SettingsView.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: LoginView,
      meta: { requiresAuth: false },
    },
    {
      path: '/users',
      name: 'UserList',
      component: UserListView,
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/users/new',
      name: 'UserCreate',
      component: UserCreateView,
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/users/:username',
      name: 'UserDetail',
      component: UserDetailView,
      meta: { requiresAuth: true },
    },
    {
      path: '/users/:username/edit',
      name: 'UserEdit',
      component: UserEditView,
      meta: { requiresAuth: true },
    },
    {
      path: '/tasks',
      name: 'TaskList',
      component: TaskListView,
      meta: { requiresAuth: true },
    },
    {
      path: '/settings',
      name: 'Settings',
      component: SettingsView,
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      // ルートパスはタスク一覧へリダイレクト
      path: '/',
      redirect: '/tasks',
    },
  ],
})

// ナビゲーションガード: 認証チェックと権限チェック
router.beforeEach((to) => {
  const auth = useAuthStore()

  // 認証が必要なページへの未認証アクセスはログイン画面へ
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return '/login'
  }

  // ログイン済みでログイン画面にアクセスした場合はリダイレクト
  if (to.path === '/login' && auth.isAuthenticated) {
    return auth.isAdmin ? '/users' : '/tasks'
  }

  // admin 権限が必要なページへの一般ユーザーアクセスはタスク一覧へ
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return '/tasks'
  }

  // 一般ユーザーが他ユーザーの詳細・編集ページへアクセスしようとする場合はリダイレクト
  if (
    auth.isAuthenticated &&
    !auth.isAdmin &&
    (to.name === 'UserDetail' || to.name === 'UserEdit')
  ) {
    const targetUsername = to.params.username as string
    if (targetUsername !== auth.currentUsername) {
      return '/tasks'
    }
  }

  return true
})

export default router
