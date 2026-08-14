<template>
  <div class="login-page">
    <div class="left-panel">
      <div class="panel-bg"></div>
      <div class="panel-decoration dec-1"></div>
      <div class="panel-decoration dec-2"></div>
      <div class="panel-decoration dec-3"></div>

      <div class="brand-header">
        <div class="brand-info">
          <span class="brand-name">彩迹熊智能学习助手</span>
          <span class="brand-slogan">AI-Powered Learning Assistant</span>
        </div>
      </div>

      <div class="brand-content">
        <div class="hero-section">
          <h1 class="main-title">智能驱动</h1>
          <h1 class="main-title highlight">高效学习</h1>
          <p class="brand-desc">基于先进人工智能技术，为您提供个性化的学习路径和智能问答服务</p>
        </div>
        
        <div class="feature-list">
          <div class="feature-item" v-for="(feature, index) in features" :key="index">
            <div class="feature-icon-wrap">
              <el-icon :size="18" class="feature-icon"><component :is="feature.icon" /></el-icon>
            </div>
            <div class="feature-content">
              <span class="feature-title">{{ feature.title }}</span>
              <span class="feature-text">{{ feature.desc }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <div class="brand-footer">
        <p>© 2026 彩迹熊 · 让学习更智慧</p>
      </div>
    </div>
    
    <div class="right-panel">
      <div class="form-container">
        <div class="form-header">
          <div class="header-content">
            <h2 class="form-title">{{ isLogin ? '欢迎回来' : '创建账号' }}</h2>
            <p class="form-subtitle">{{ isLogin ? '登录您的账号开始学习之旅' : '注册新账号开启智慧学习' }}</p>
          </div>
          <div class="tab-switch">
            <button 
              class="tab-btn" 
              :class="{ active: isLogin }"
              @click="isLogin = true"
            >
              登录
            </button>
            <button 
              class="tab-btn" 
              :class="{ active: !isLogin }"
              @click="isLogin = false"
            >
              注册
            </button>
          </div>
        </div>
        
        <el-form ref="formRef" :model="form" :rules="rules" class="login-form">
          <template v-if="isLogin">
            <el-form-item prop="username">
              <el-input
                v-model="form.username"
                placeholder="请输入用户名"
                size="large"
                class="form-input"
                :prefix-icon="User"
              />
            </el-form-item>
            
            <el-form-item prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="请输入密码"
                size="large"
                class="form-input"
                :prefix-icon="Lock"
                show-password
              />
            </el-form-item>
            
            <div class="form-options">
              <el-checkbox v-model="rememberMe" class="remember-checkbox">记住我</el-checkbox>
              <a href="javascript:void(0)" class="forgot-link" @click="handleForgotPassword">忘记密码？</a>
            </div>
            
            <el-form-item>
              <el-button
                type="primary"
                size="large"
                class="submit-btn"
                :loading="loading"
                @click="handleLogin"
              >
                登 录
              </el-button>
            </el-form-item>
          </template>
          
          <template v-else>
            <el-form-item prop="username">
              <el-input
                v-model="form.username"
                placeholder="请输入用户名"
                size="large"
                class="form-input"
                :prefix-icon="User"
              />
            </el-form-item>
            
            <el-form-item prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="请输入密码（至少6位）"
                size="large"
                class="form-input"
                :prefix-icon="Lock"
                show-password
              />
            </el-form-item>
            
            <el-form-item prop="confirmPassword">
              <el-input
                v-model="form.confirmPassword"
                type="password"
                placeholder="请确认密码"
                size="large"
                class="form-input"
                :prefix-icon="Lock"
                show-password
              />
            </el-form-item>
            
            <el-form-item prop="email">
              <el-input
                v-model="form.email"
                placeholder="请输入邮箱"
                size="large"
                class="form-input"
                :prefix-icon="Message"
              />
            </el-form-item>
            
            <el-form-item>
              <el-checkbox v-model="agreeTerms" class="agree-checkbox">
                我已阅读并同意
                <a href="#" class="link-text">用户服务协议</a>
                和
                <a href="#" class="link-text">隐私政策</a>
              </el-checkbox>
            </el-form-item>
            
            <el-form-item>
              <el-button
                type="primary"
                size="large"
                class="submit-btn"
                :loading="loading"
                @click="handleRegister"
              >
                注 册
              </el-button>
            </el-form-item>
          </template>
        </el-form>
        
        <div class="divider">
          <span class="divider-line"></span>
          <span class="divider-text">或</span>
          <span class="divider-line"></span>
        </div>
        
        <div class="quick-login">
          <el-button
            type="default"
            size="large"
            class="guest-btn student"
            :loading="loading"
            @click="handleQuickLogin('stu_001')"
          >
            <el-icon :size="18"><Reading /></el-icon>
            <span>学生账号体验</span>
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import {
  User, Lock, Message, ChatDotSquare,
  PieChart, Compass, Reading, Connection
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const chatStore = useChatStore()

const isLogin = ref(true)

onMounted(() => {
  localStorage.removeItem('isLoggedIn')
  localStorage.removeItem('userId')
})
const loading = ref(false)
const rememberMe = ref(false)
const agreeTerms = ref(false)

const features = [
  { icon: ChatDotSquare, title: '智能问答', desc: '随时随地获取知识解答' },
  { icon: PieChart, title: '学习分析', desc: '多维度洞察学习效果' },
  { icon: Compass, title: '路径规划', desc: '个性化学习方案定制' },
  { icon: Connection, title: '多语言支持', desc: '中英双语界面切换' }
]

const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  email: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度在3到20个字符之间', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 30, message: '密码长度在6到30个字符之间', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: (rule, value, callback) => {
      if (value !== form.password) {
        callback(new Error('两次输入密码不一致'))
      } else {
        callback()
      }
    }, trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ]
}

async function handleLogin() {
  loading.value = true
  try {
    await chatStore.login(form.username, form.password)
    if (rememberMe.value) {
      localStorage.setItem('remembered_user', form.username)
    } else {
      localStorage.removeItem('remembered_user')
    }
    router.push('/')
  } catch (error) {
    console.error('Login failed:', error)
    ElMessage.error(error.message || '登录失败')
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!agreeTerms.value) {
    return
  }
  loading.value = true
  setTimeout(() => {
    localStorage.setItem(`password_${form.username}`, form.password)
    chatStore.quickLogin(form.username || 'demo')
    router.push('/')
    loading.value = false
  }, 500)
}

function handleQuickLogin(userId) {
  loading.value = true
  setTimeout(() => {
    chatStore.quickLogin(userId)
    router.push('/')
    loading.value = false
  }, 500)
}

async function handleForgotPassword() {
  try {
    const { value: username } = await ElMessageBox.prompt(
      '请输入要重置密码的用户名',
      '忘记密码',
      {
        confirmButtonText: '下一步',
        cancelButtonText: '取消',
        inputPlaceholder: '用户名',
        inputPattern: /\S+/,
        inputErrorMessage: '用户名不能为空',
      }
    )
    if (!username || !username.trim()) return

    const { value: newPassword } = await ElMessageBox.prompt(
      `为「${username.trim()}」设置新密码`,
      '重置密码',
      {
        confirmButtonText: '确认重置',
        cancelButtonText: '取消',
        inputPlaceholder: '新密码（至少6位）',
        inputType: 'password',
        inputPattern: /.{6,}/,
        inputErrorMessage: '密码至少6位',
      }
    )
    if (!newPassword || newPassword.length < 6) {
      ElMessage.error('密码至少6位')
      return
    }

    localStorage.setItem(`password_${username.trim()}`, newPassword)
    ElMessage.success('密码已重置，请用新密码登录')
  } catch {
    // 用户取消，忽略
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
  overflow: hidden;
}

.left-panel {
  flex: 1;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 50%, #eef2ff 100%);
  padding: 50px 60px;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.panel-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    radial-gradient(ellipse at 20% 20%, rgba(99, 102, 241, 0.08) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 80%, rgba(139, 92, 246, 0.08) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 50%, rgba(167, 139, 250, 0.05) 0%, transparent 70%);
}

.panel-decoration {
  position: absolute;
  border-radius: 50%;
  opacity: 0.06;
}

.dec-1 {
  width: 500px;
  height: 500px;
  background: #6366f1;
  top: -150px;
  right: -100px;
}

.dec-2 {
  width: 300px;
  height: 300px;
  background: #8b5cf6;
  bottom: -80px;
  left: -50px;
}

.dec-3 {
  width: 200px;
  height: 200px;
  background: #a78bfa;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}


.brand-header {
  display: flex;
  align-items: center;
  gap: 14px;
  z-index: 1;
  margin-bottom: auto;
}

.brand-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-name {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
}

.brand-slogan {
  font-size: 12px;
  color: #94a3b8;
  letter-spacing: 0.5px;
}

.brand-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  z-index: 1;
}

.hero-section {
  margin-bottom: 48px;
}

.main-title {
  font-size: 52px;
  font-weight: 800;
  color: #0f172a;
  margin: 0;
  letter-spacing: -1.5px;
  line-height: 1.1;
}

.main-title.highlight {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a78bfa 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.brand-desc {
  font-size: 16px;
  color: #64748b;
  margin: 16px 0 0;
  max-width: 400px;
  line-height: 1.6;
}

.feature-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.feature-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 20px;
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(10px);
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.8);
  transition: all 0.3s ease;
}

.feature-item:hover {
  transform: translateX(8px);
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.1);
}

.feature-icon-wrap {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.feature-icon {
  color: #6366f1;
}

.feature-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.feature-title {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.feature-text {
  font-size: 13px;
  color: #64748b;
}

.brand-footer {
  z-index: 1;
  margin-top: auto;
  
  p {
    font-size: 12px;
    color: #94a3b8;
    margin: 0;
  }
}

.right-panel {
  width: 480px;
  background: #fff;
  padding: 50px 56px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative;
}

.right-panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 4px;
  background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #a78bfa 100%);
}

.form-container {
  width: 100%;
}

.form-header {
  margin-bottom: 36px;
}

.header-content {
  margin-bottom: 28px;
}

.form-title {
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 8px;
}

.form-subtitle {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

.tab-switch {
  display: flex;
  background: #f1f5f9;
  border-radius: 12px;
  padding: 4px;
}

.tab-btn {
  flex: 1;
  background: transparent;
  border: none;
  font-size: 14px;
  font-weight: 600;
  color: #64748b;
  padding: 12px 16px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.tab-btn.active {
  background: #fff;
  color: #6366f1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.tab-btn:hover {
  color: #6366f1;
}

.login-form {
  margin-bottom: 20px;
}

.form-input {
  border-radius: 12px;
  height: 50px;
  
  :deep(.el-input__wrapper) {
    border-radius: 12px;
    box-shadow: none;
    border-color: #e2e8f0;
    transition: all 0.3s ease;
    background: #fafbfc;
    
    &:hover {
      border-color: #cbd5e1;
    }
    
    &.is-focus {
      border-color: #6366f1;
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
      background: #fff;
    }
  }
  
  :deep(.el-input__inner) {
    font-size: 14px;
  }
  
  :deep(.el-input__prefix) {
    color: #94a3b8;
  }
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.remember-checkbox {
  font-size: 14px;
  color: #64748b;
  
  :deep(.el-checkbox__label) {
    color: #64748b;
  }
  
  :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
    background-color: #6366f1;
    border-color: #6366f1;
  }
}

.forgot-link {
  font-size: 14px;
  color: #6366f1;
  text-decoration: none;
  
  &:hover {
    text-decoration: underline;
  }
}

.submit-btn {
  width: 100%;
  height: 50px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border: none;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
  transition: all 0.3s ease;
  
  :deep(.el-button__text) {
    color: #fff;
  }
  
  &:hover:not(:disabled) {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
    transform: translateY(-1px);
  }
  
  &:active:not(:disabled) {
    transform: translateY(0);
  }
}

.agree-checkbox {
  font-size: 12px;
  color: #64748b;
  
  :deep(.el-checkbox__label) {
    color: #64748b;
  }
  
  :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
    background-color: #6366f1;
    border-color: #6366f1;
  }
}

.link-text {
  color: #6366f1;
  text-decoration: none;
  
  &:hover {
    text-decoration: underline;
  }
}

.divider {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 24px 0;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #e2e8f0, transparent);
}

.divider-text {
  font-size: 13px;
  color: #94a3b8;
}

.quick-login {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.guest-btn {
  width: 100%;
  height: 46px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  border-color: #e2e8f0;
  color: #475569;
  background: #fafbfc;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.3s ease;
  
  &:hover {
    border-color: #6366f1;
    color: #6366f1;
    background: #f5f3ff;
  }
  
  &.student {
    border-color: rgba(99, 102, 241, 0.3);
    color: #6366f1;
    background: rgba(99, 102, 241, 0.05);
    
    &:hover {
      background: rgba(99, 102, 241, 0.1);
      border-color: #6366f1;
    }
  }
}

@media (max-width: 900px) {
  .left-panel {
    display: none;
  }
  
  .right-panel {
    width: 100%;
    padding: 40px 32px;
  }
  
  .form-title {
    font-size: 24px;
  }
  
  .main-title {
    font-size: 36px;
  }
}

@media (max-width: 480px) {
  .right-panel {
    padding: 30px 24px;
  }
  
  .form-title {
    font-size: 22px;
  }
  
  .tab-btn {
    font-size: 13px;
    padding: 10px 12px;
  }
  
  .form-input {
    height: 46px;
  }
  
  .submit-btn {
    height: 46px;
    font-size: 15px;
  }
}
</style>