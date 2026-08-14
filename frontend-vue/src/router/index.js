import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '@/views/ChatView.vue'
import LoginView from '@/views/LoginView.vue'

const routes = [
  { 
    path: '/login', 
    name: 'login', 
    component: LoginView,
    meta: { requiresAuth: false }
  },
  { 
    path: '/', 
    name: 'chat', 
    component: ChatView,
    meta: { requiresAuth: true }
  },
  { 
    path: '/profile', 
    name: 'profile', 
    component: () => import('@/views/ProfileView.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/agents', 
    name: 'agents', 
    component: () => import('@/views/AgentsView.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/knowledge', 
    name: 'knowledge', 
    component: () => import('@/views/KnowledgeView.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/settings', 
    name: 'settings', 
    component: () => import('@/views/SettingsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/report/:userId?',
    name: 'report',
    component: () => import('@/views/ReportView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/practice',
    name: 'practice',
    component: () => import('@/views/PracticeView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/skill-gap',
    name: 'skill-gap',
    component: () => import('@/views/SkillGapView.vue'),
    meta: { requiresAuth: true }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export function setupRouterGuard(app) {
  router.beforeEach((to, from, next) => {
    const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true'
    
    if (to.meta.requiresAuth && !isLoggedIn) {
      next('/login')
    } else if (to.path === '/login' && isLoggedIn) {
      next('/')
    } else {
      next()
    }
  })
}

export default router
