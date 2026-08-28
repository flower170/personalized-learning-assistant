import { defineStore } from 'pinia'
import { ref, computed, watch, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { chatApi, profileApi, onlinePathApi, practiceApi, onboardingApi } from '@/api'
import { messages as localeMessages } from '@/locales/index.js'

export const useChatStore = defineStore('chat', () => {
  // ========== 状态 ==========
  const messages = ref([])
  const loading = ref(false)
  const sessionId = ref('sess_' + Date.now())
  const userId = ref('stu_001')
  const userName = ref('')
  const userGrade = ref('')
  const userMajor = ref('')

  // 画像
  const profile = ref(null)
  const radarData = ref([])

  // 新手引导状态（画像→路径→资源；每步可跳过）——来自 GET /onboarding/{userId}
  const onboarding = ref(null)

  // 流式输出（单条文本流）
  const streamingText = ref('')

  // 资源生成进度
  const resourceProgress = ref({})

  // 智能体执行节点追踪 Map<nodeName, {status, elapsed_ms, content_chars, rag_sources_count, used_fallback}>
  const agentNodeMap = ref({})

  // 最近会话列表（从 localStorage 加载）
  const sessions = ref([])

  function loadSessions() {
    try {
      const key = `chat_sessions_${userId.value}`
      const raw = localStorage.getItem(key)
      if (raw) {
        const data = JSON.parse(raw)
        if (Array.isArray(data)) {
          sessions.value = data
          return
        }
      }
    } catch {}
    sessions.value = []
  }

  // 初始化加载会话
  loadSessions()

  const sidebarCollapsed = ref(false)

  // 追踪上一轮对话意图（用于画像等多轮对话保持模式）
  const currentIntent = ref('')

  // 学习路径向导请求：ChatView 监听后打开交互式向导（{topic} 或 null）
  const pathWizardRequest = ref(null)

  // 上传文件状态
  const tempFileId = ref('')
  const fileUploading = ref(false)
  const uploadedFiles = ref([])

  function setTempFileId(id) { tempFileId.value = id }
  function setFileUploading(v) { fileUploading.value = v }
  function addUploadedFile(file) {
    const exists = uploadedFiles.value.find(f => f.id === file.id)
    if (!exists) uploadedFiles.value.push(file)
  }

  function addSystemMessage(content) {
    messages.value.push({
      role: 'assistant',
      content,
      timestamp: Date.now(),
      isSystem: true,
    })
  }

  // 登录状态
  const isLoggedIn = ref(localStorage.getItem('isLoggedIn') === 'true')

  // 主题和语言
  const theme = ref(localStorage.getItem('theme') || 'default')
  const language = ref(localStorage.getItem('language') || 'zh-CN')

  const themeOptions = [
    { value: 'default', label: '默认', preview: '⚪' },
    { value: 'cream', label: '米色', preview: '⚪' },
    { value: 'dark', label: '深色', preview: '⚫' },
    { value: 'glass', label: '玻璃', preview: '🟣' },
  ]

  const languageOptions = [
    { value: 'zh-CN', label: '中文' },
    { value: 'en-US', label: 'English' },
  ]

  const speechLanguage = ref(localStorage.getItem('speechLanguage') || 'zh-CN')

  const speechLanguageOptions = [
    { value: 'zh-CN', label: '简体中文', flag: '🇨🇳' },
    { value: 'en-US', label: 'English', flag: '🇺🇸' },
  ]

  const currentLocale = computed(() => {
    return localeMessages[language.value] || localeMessages['zh-CN']
  })

  function getLocale(path) {
    const parts = path.split('.')
    let result = currentLocale.value
    for (const part of parts) {
      result = result?.[part]
      if (!result) break
    }
    return result || path
  }

  // ========== 计算属性 ==========
  const usernameDisplay = computed(() => {
    return profile.value?.name || userName.value || userId.value
  })

  // ========== 登录/登出 ==========
  function login(username, password) {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        const storedPassword = localStorage.getItem(`password_${username}`)
        if (!storedPassword) {
          reject(new Error('该账号尚未注册，请先注册'))
          return
        }
        if (storedPassword !== password) {
          reject(new Error('密码错误'))
          return
        }
        userId.value = username
        isLoggedIn.value = true
        localStorage.setItem('isLoggedIn', 'true')
        localStorage.setItem('userId', username)
        loadSessions()
        fetchOnboarding()
        resolve()
      }, 500)
    })
  }

  const ALLOWED_QUICK_LOGIN_STORE = new Set(['stu_001'])
  function quickLogin(userIdValue) {
    // 允许两类账号：① 体验白名单 ② 已成功注册（localStorage 有 password_xxx）
    if (!ALLOWED_QUICK_LOGIN_STORE.has(userIdValue) && !localStorage.getItem(`password_${userIdValue}`)) {
      throw new Error('该账号未注册')
    }
    userId.value = userIdValue
    isLoggedIn.value = true
    localStorage.setItem('isLoggedIn', 'true')
    localStorage.setItem('userId', userIdValue)
    // stu_001 体验账号：预填默认基础信息，保证画像初始化不为空
    if (userIdValue === 'stu_001') {
      userName.value = '学生体验账号'
      userGrade.value = '大二'
      userMajor.value = '计算机科学与技术'
    } else {
      // 新注册账号：没填的信息先保留空，等后续画像采集或设置页补齐
      if (!userName.value) userName.value = ''
    }
    loadSessions()
    messages.value = []
    currentIntent.value = ''
    tempFileId.value = ''
    sessionId.value = 'sess_' + Date.now()
    agentNodeMap.value = {}
    fetchOnboarding()
  }

  function logout() {
    try {
      localStorage.removeItem(`chat_sessions_${userId.value}`)
      for (const sess of sessions.value) {
        localStorage.removeItem(`chat_history_${userId.value}_${sess.id}`)
      }
    } catch {}
    isLoggedIn.value = false
    localStorage.removeItem('isLoggedIn')
    localStorage.removeItem('userId')
    userId.value = ''
    userName.value = ''
    userGrade.value = ''
    userMajor.value = ''
    profile.value = null
    radarData.value = []
    messages.value = []
    sessions.value = []
    sessionId.value = 'sess_' + Date.now()
    agentNodeMap.value = {}
    onboarding.value = null
  }

  // ========== 时间格式化 ==========
  function formatTime(timestamp) {
    const now = Date.now()
    const diff = now - timestamp

    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days < 7) return `${days}天前`
    return new Date(timestamp).toLocaleDateString('zh-CN')
  }

  // ========== SSE 解析辅助 ==========
  async function parseSSEStream(response, onEvent) {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const raw = line.slice(6)
          if (raw === '[DONE]') continue
          try {
            const event = JSON.parse(raw)
            onEvent(event)
          } catch {
            /* ignore malformed JSON */
          }
        }
      }
    }
  }

  // ========== 视频关键词检测 ==========
  const VIDEO_KEYWORDS = [
    '视频推荐', '推荐视频', '视频教程', '学习视频', '教学视频',
    '视频讲解', '给我视频', '找视频', '搜视频', '相关视频',
    'b站', 'bilibili', 'B站', '哔哩哔哩', '哔站',
  ]

  function isVideoRequest(text) {
    const lower = text.toLowerCase()
    // 1. 精确关键词
    if (VIDEO_KEYWORDS.some(kw => lower.includes(kw))) return true
    // 2. 同时包含"视频"和推荐意图词
    if (lower.includes('视频')) {
      const recWords = ['推荐', '给我', '帮我', '找', '搜索', '有什么', '看看']
      if (recWords.some(w => lower.includes(w))) return true
    }
    return false
  }

  // ========== 发送消息（智能路由） ==========
  async function sendMessage(text, explicitType = '', singleResourceType = '') {
    if (!text.trim() || loading.value) return

    // 视频关键词自动检测：未指定类型时，自动只生成视频
    if (!explicitType && !singleResourceType && isVideoRequest(text)) {
      explicitType = 'resource'
      singleResourceType = 'video'
    }

    // 画像多轮对话：仅在消息明显不是"生成资料/出题"等其他意图时才延续 profile
    const looksLikeResource = /生成|资料|出题|题目|导图|课件|文档|教程|视频|路径|规划|推荐/.test(text)
    if (!explicitType && currentIntent.value === 'profile' && sessionId.value && !looksLikeResource) {
      explicitType = 'profile'
    }

    // 资源澄清对话延续：如果上一轮是 resource 模式，自动延续
    if (!explicitType && currentIntent.value === 'resource') {
      explicitType = 'resource'
    }

    messages.value.push({ role: 'user', content: text, timestamp: Date.now() })

    // 如果没有会话，创建新会话
    let sess = sessions.value.find(s => s.id === sessionId.value)
    if (!sess) {
      const now = Date.now()
      sess = {
        id: sessionId.value,
        title: text.length > 20 ? text.slice(0, 20) + '...' : text,
        time: '刚刚',
        timestamp: now,
      }
      sessions.value.unshift(sess)
    } else if (sess.title === '新对话' && text.length > 0) {
      sess.title = text.length > 20 ? text.slice(0, 20) + '...' : text
    }
    // 更新会话时间
    sess.time = formatTime(Date.now())
    sess.timestamp = Date.now()

    loading.value = true
    streamingText.value = ''

    // 根据 explicitType 路由到不同的处理方式
    try {
      if (tempFileId.value && explicitType !== 'resource') {
        // ✅ 有上传文件且不是显式要求生成资源 → 走知识库直答
        await sendKbChat(text)
      } else if (explicitType === 'resource') {
        if (singleResourceType) {
          // ✅ 已指定具体资源类型 → 直接 SSE 生成
          await sendResourceStream(text, singleResourceType)
        } else {
          // ✅ 未指定类型 → 走智能体对话引导（ResourceTypeDetectAgent）
          await sendNormalChat(text, 'resource')
        }
      } else if (explicitType === 'plan') {
        // 学习路径统一走交互式向导（画像起步 → 信息不足提问 → 草案确认）
        pathWizardRequest.value = { topic: extractPathTopic(text) }
      } else if (explicitType === 'profile') {
        await sendProfileChat(text)
      } else {
        // 默认走 LangGraph 统一聊天
        await sendNormalChat(text, explicitType)
      }
    } catch (err) {
      messages.value.push({
        role: 'assistant',
        content: `请求失败: ${err.message}`,
        isError: true,
        timestamp: Date.now(),
      })
    } finally {
      loading.value = false
      streamingText.value = ''
    }
  }

  // ========== 普通聊天（走 LangGraph） ==========
  async function sendNormalChat(text, explicitType) {
    const res = await chatApi.send(userId.value, text, sessionId.value, explicitType, speechLanguage.value, tempFileId.value)

    // 记录当前意图，用于多轮对话延续
    currentIntent.value = res.intent || ''

    // ✅ 资源意图：智能体通过自然对话引导选择，不使用按钮
    if (res.intent === 'resource') {

      // ✅ 类型已确定 → 直接触发 SSE 生成（跳过中间的确认消息）
      if (res.resource_type_to_generate) {
        await sendResourceStream(text, res.resource_type_to_generate)
        currentIntent.value = ''
        return
      }

      // ✅ 后端返回的是 resource_types 数组 → 直接生成
      if (res.resource_types && res.resource_types.length > 0) {
        // 多种类型（如5类全量）→ 传空类型，让 sendResourceStream 生成全部
        const single = res.resource_types.length === 1 ? res.resource_types[0] : ''
        const topic = res.resource_topic || text
        await sendResourceStream(topic, single)
        currentIntent.value = ''
        return
      }

      // ✅ 类型不明确 → 展示智能体的引导询问，让用户自然回复
      const reply = res.reply || '好的，你想了解哪方面的内容呢？'

      streamingText.value = ''
      for (let i = 0; i < reply.length; i++) {
        streamingText.value += reply[i]
        await new Promise(r => setTimeout(r, 15))
      }

      messages.value.push({
        role: 'assistant',
        content: reply,
        timestamp: Date.now(),
        intent: 'resource',
        // ⛔ 不使用 suggestions 按钮，智能体通过对话引导
      })

      return
    }

    // ✅ 路径规划意图：调用专门的路径规划接口
    if (res.intent === 'plan') {
      // 检查对话历史中是否已有学习计划（避免追问时重复生成新计划）
      const existingPlan = messages.value.find(m => m.intent === 'plan' && m.content && m.content.length > 100)
      // 判断是否为追问（消息短且含疑问词，或已有计划时的简短消息）
      const isFollowUp = existingPlan && (
        text.length < 20 ||
        /[?？么吗什怎哪多]/.test(text) ||
        /第[\d一二三四五六七八九十]+天/.test(text)
      )
      if (!isFollowUp) {
        // 非追问 → 打开交互式学习路径向导（画像起步，信息不足提问补充）
        pathWizardRequest.value = { topic: extractPathTopic(text) }
        currentIntent.value = ''
        return
      }
      // 是追问 → 绕过 LangGraph 意图检测，直接走辅导接口（tutor）
      const planSummary = existingPlan.content.slice(0, 1500)
      const tutorQuestion = `我有一个学习计划，请根据这个计划回答我的问题。\n\n计划内容：\n${planSummary}\n\n问题：${text}\n\n请给出具体、可执行的第一天学习建议。`
      // 用 tutor API 直接提问（不走 LangGraph 意图分类）
      const tutorResp = await fetch('http://127.0.0.1:8000/api/tutor/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_id: userId.value,
          question: tutorQuestion,
          conversation_history: [],
        }),
      })
      let tutorReply = ''
      if (tutorResp.ok) {
        const reader = tutorResp.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() || ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const payload = line.slice(6).trim()
            if (payload === '[DONE]') continue
            try {
              const evt = JSON.parse(payload)
              if (evt.chunk) {
                tutorReply += evt.chunk
                streamingText.value = tutorReply
              }
            } catch { /* skip */ }
          }
        }
      }
      if (!tutorReply) {
        tutorReply = '请根据上面的学习计划回答我的问题。'
      }
      messages.value.push({
        role: 'assistant',
        content: tutorReply,
        timestamp: Date.now(),
        intent: 'tutor',
      })
      return
    }

    const reply = res.reply || '处理完成'

    // 模拟流式打字效果
    streamingText.value = ''
    for (let i = 0; i < reply.length; i++) {
      streamingText.value += reply[i]
      await new Promise(r => setTimeout(r, 15))
    }

    // 构建消息对象
    const msg = {
      role: 'assistant',
      content: reply,
      timestamp: Date.now(),
      intent: res.intent,
    }

    // ⛔ 移除所有建议按钮，引导全部通过自然对话完成
    // （后端智能体会在回复中自然引导用户下一步操作）

    messages.value.push(msg)

    if (res.session_id) sessionId.value = res.session_id
    if (res.is_completed) fetchProfile()
  }

  // ========== 知识库文件直答（SSE 流式） ==========
  async function sendKbChat(question) {
    const msgIdx = messages.value.length
    messages.value.push({
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    })
    streamingText.value = '正在查询文档...'
    try {
      const resp = await fetch('http://127.0.0.1:8000/api/kb/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: question,
          student_id: userId.value,
          session_id: sessionId.value,
          temp_file_id: tempFileId.value,
        }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let content = ''
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() || ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const payload = line.slice(6).trim()
            if (payload === '[DONE]') break
            try {
              const evt = JSON.parse(payload)
              if (evt.event === 'handshake') {
                streamingText.value = evt.is_local ? '正在检索本地文档...' : '正在查询讯飞知识库...'
                continue
              }
              if (evt.chunk) { content += evt.chunk; messages.value[msgIdx].content = content }
              if (evt.error) { content += `\n\n❌ ${evt.error}`; messages.value[msgIdx].content = content }
            } catch (parseErr) {
              console.warn('[KB SSE] JSON解析失败:', line, parseErr)
            }
          }
        }
      } catch (streamErr) {
        console.error('[KB SSE] 流读取异常:', streamErr)
        const errMsg = streamErr?.name === 'AbortError' ? '请求被中断' : (streamErr?.message || String(streamErr))
        content += `\n\n⚠️ 连接中断: ${errMsg}`
        messages.value[msgIdx].content = content
      }
      if (!content) messages.value[msgIdx].content = '(未获得回答)'
    } catch (e) {
      messages.value[msgIdx].content = `❌ 知识库查询失败: ${e.message}`
    } finally {
      streamingText.value = ''
      loading.value = false
    }
  }

  async function fetchAssistantIntro() {
    streamingText.value = '正在生成介绍...'
    let reply = ''
    try {
      const { systemApi } = await import('@/api/index.js')
      const result = await systemApi.assistantIntro()
      reply = (result && result.reply) ? result.reply : '你好！我是彩迹熊 AI 学习助手，可以帮你构建学习画像、生成学习资料、制定学习路径、解答学习问题。有什么需要帮助的吗？😊'
    } catch (err) {
      console.error('[fetchAssistantIntro] 调用失败:', err)
      reply = '你好！我是彩迹熊 AI 学习助手，很高兴为你服务！我可以帮你：\n\n1. 📋 **构建学习画像** — 了解你的基础，给出个性化建议\n2. 📚 **生成学习资料** — 讲义、思维导图、练习题、代码示例、视频清单\n3. 🗺️ **制定学习路径** — 按你的目标和时间安排每日学习计划\n4. 💡 **解答学习问题** — 上传文档后针对文档内容提问\n\n有什么我可以帮你的吗？😊'
    } finally {
      streamingText.value = ''
      if (reply) {
        messages.value.push({
          id: Date.now(),
          role: 'assistant',
          content: reply,
          time: new Date().toLocaleString('zh-CN'),
        })
      }
      try {
        const sessions = JSON.parse(localStorage.getItem(`chat_sessions_${userId.value}`) || '[]')
        let cur = sessions.find(s => s.id === sessionId.value)
        if (!cur) {
          cur = { id: sessionId.value, title: messages.value[0]?.content?.slice(0, 20) || '新对话', time: Date.now() }
          sessions.unshift(cur)
          localStorage.setItem(`chat_sessions_${userId.value}`, JSON.stringify(sessions))
        }
        localStorage.setItem(`chat_history_${userId.value}_${sessionId.value}`, JSON.stringify(messages.value))
      } catch {}
    }
  }

  // ========== 资源生成（SSE 流式，富内容） ==========

  /** 取练习题内容的「中文展示部分」：把 ```json / 裸 JSON 块从展示里剥掉，只留中文正文。
   *  模型按新提示词会先出中文、最后出 JSON；旧顺序（JSON 在前）也能兼容：
   *  - 完整围栏块 → 整体移除
   *  - 未闭合围栏（JSON 正在流式生成）→ 丢弃其后所有（此时无中文可看，表现为等待）
   *  - 裸 JSON（漏写围栏）→ 按 "exercises" 标记把所在最外层 { ... } 剥掉（完整或进行中都行） */
  function exerciseTail(text) {
    if (!text) return ''
    let t = text.replace(/```json\s*\n?[\s\S]*?```/g, '')   // 完整围栏块
    t = t.replace(/```json\s*\n?[\s\S]*$/, '')              // 未闭合围栏及其后
    const exIdx = t.indexOf('"exercises"')
    if (exIdx !== -1) {
      let left = -1, depth = 0
      for (let i = exIdx; i >= 0; i--) {
        const ch = t[i]
        if (ch === '}') depth++
        else if (ch === '{') {
          depth--
          if (depth <= 0) { left = i; break }
        }
      }
      if (left !== -1) {
        let right = t.length
        depth = 0
        for (let i = left; i < t.length; i++) {
          const ch = t[i]
          if (ch === '{') depth++
          else if (ch === '}') {
            depth--
            if (depth === 0) { right = i + 1; break }
          }
        }
        t = t.slice(0, left) + t.slice(right)
      }
    }
    return t
  }

  async function sendResourceStream(topic, singleType) {
    // 消息懒创建：思考阶段（画像分析 / RAG 检索）不出现组件，首个内容块到达时才创建并随内容一起流式显示
    let msgIdx = -1
    function ensureMsg() {
      if (msgIdx !== -1) return
      msgIdx = messages.value.length
      messages.value.push({
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        intent: 'resource',
        sections: [],
        imageUrls: {},
      })
    }

    streamingText.value = '正在思考'
    agentNodeMap.value = {}

    try {
      const types = singleType ? [singleType] : ['lecture', 'mindmap', 'exercise', 'reading', 'code']
      const body = JSON.stringify({
        student_id: userId.value,
        topic: topic,
        resource_types: types,
        language: speechLanguage.value,
        temp_file_id: tempFileId.value || undefined,
      })
      console.log('[SSE] 发送资源请求:', topic, types)

      const response = await fetch('http://127.0.0.1:8000/api/dispatch/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })

      console.log('[SSE] 响应状态:', response.status)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const RESOURCE_LABELS = {
        lecture: '📚 课程讲解文档',
        mindmap: '🖼️ 知识点思维导图',
        exercise: '📝 练习题目',
        reading: '📖 拓展阅读材料',
        code: '💻 代码实操案例',
        video: '🎬 视频教程推荐',
      }

      // C 功能：生成完后根据类型给出自然引导
      const NEXT_STEP_GUIDES = {
        lecture: '已经为你生成了课程讲解！如果想巩固一下，可以告诉我需要练习题或代码案例😊',
        mindmap: '思维导图已经梳理好了！接下来想看详细的课程讲解，还是做几道练习题练练手？',
        exercise: '练习题已就绪！如果某个题目不太明白，随时问我。需要我生成对应的课程讲解吗？',
        reading: '阅读材料已为你准备好！如果想动手实践，我可以生成代码案例或练习题。',
        code: '代码案例已生成！建议结合课程讲解一起学习，需要我生成吗？',
        video: '视频推荐已完成！看完视频后，可以做练习题来检验学习成果哦～',
      }

      let currentType = ''
      let currentSection = ''
      let pendingHeader = ''  // start 事件只暂存资源标题，首个内容块到达时才创建消息（避免空框闪现）
      let typeImages = {}
      let videoCovers = {}  // url → cover_url 映射

      // ===== 智能体节点追踪 =====
      // 根据 stage 或 type 映射到标准节点名
      const stageToNode = {
        analyze_profile: 'profile_analyze',
        rag_retrieve: 'rag_retrieve',
        generate_resource: null,
        post_process: 'post_process',
        complete: 'post_process',
      }
      const typeToNode = {
        lecture: 'lecture_gen',
        mindmap: 'mindmap_gen',
        exercise: 'exercise_gen',
        code: 'code_gen',
        video: 'video_gen',
        reading: 'lecture_gen',
      }
      function _trackNode(event2) {
        let nodeName = null
        if (event2.stage && stageToNode[event2.stage]) {
          nodeName = stageToNode[event2.stage]
        }
        if (!nodeName && event2.type && typeToNode[event2.type]) {
          nodeName = typeToNode[event2.type]
        }
        if (!nodeName && event2.event === 'resource_progress') {
          if ((event2.data || '').includes('检索')) nodeName = 'rag_retrieve'
        }
        if (!nodeName) return
        const prev = agentNodeMap.value[nodeName] || {}
        const now = Date.now()
        if (event2.event === 'start' || event2.event === 'resource_start' || (event2.event === 'resource_progress' && !prev.status)) {
          agentNodeMap.value = {
            ...agentNodeMap.value,
            [nodeName]: { ...prev, status: 'running', _start_ms: now, elapsed_ms: prev.elapsed_ms || 0 }
          }
        } else if (event2.event === 'chunk') {
          const chars = (event2.data || '').length
          agentNodeMap.value = {
            ...agentNodeMap.value,
            [nodeName]: {
              ...prev,
              status: 'running',
              content_chars: (prev.content_chars || 0) + chars,
              elapsed_ms: prev._start_ms ? now - prev._start_ms : (prev.elapsed_ms || 0)
            }
          }
        } else if (event2.event === 'end' || event2.event === 'complete') {
          const usedFb = !!(event2.content && event2.content.length > 0 && prev.status === 'degraded')
          agentNodeMap.value = {
            ...agentNodeMap.value,
            [nodeName]: {
              ...prev,
              status: event2.event === 'complete' ? 'done' : (prev.status === 'error' ? 'error' : 'done'),
              elapsed_ms: prev._start_ms ? now - prev._start_ms : (prev.elapsed_ms || 0),
              used_fallback: usedFb || prev.used_fallback || false
            }
          }
        } else if (event2.event === 'error') {
          agentNodeMap.value = {
            ...agentNodeMap.value,
            [nodeName]: {
              ...prev,
              status: 'error',
              elapsed_ms: prev._start_ms ? now - prev._start_ms : (prev.elapsed_ms || 0)
            }
          }
        }
      }

      await parseSSEStream(response, (event) => {
        _trackNode(event)
        if (event.event === 'error') {
          ensureMsg()
          messages.value[msgIdx].content += `\n\n❌ ${event.message}`
          return
        }

        if (event.event === 'start') {
          currentType = event.type || ''
          currentSection = ''
          // 懒创建：只暂存标题，不创建消息、不设空大纲。等首个 chunk 到达时再创建消息，
          // 让思维导图组件和内容一起出现并流式渲染，避免思考阶段先闪现一个空的思维导图框
          pendingHeader = `## ${RESOURCE_LABELS[currentType] || currentType}\n\n`
        }

        // 内容块
        if (event.event === 'chunk' && event.data) {
          ensureMsg()
          // 首个内容块到达时补上资源标题（start 事件只暂存了标题）
          if (pendingHeader) {
            const separator = messages.value[msgIdx].content ? '\n\n---\n\n' : ''
            messages.value[msgIdx].content += `${separator}${pendingHeader}`
            pendingHeader = ''
          }
          messages.value[msgIdx].content += event.data
          // 思维导图：流式累积大纲，导图渐进渲染（不提前显示全部文字）
          if (currentType === 'mindmap') {
            messages.value[msgIdx].mindmapOutline = (messages.value[msgIdx].mindmapOutline || '') + event.data
          }
          // 练习类型：流式中只展示中文正文，不预显 JSON（答题卡在流式结束后再出）
          if (currentType === 'exercise') {
            messages.value[msgIdx].displayContent = exerciseTail(messages.value[msgIdx].content)
          }
          // 更新流式文本预览
          streamingText.value = `正在生成${RESOURCE_LABELS[currentType] || currentType}...`
        }

        // 资源类型完成
        if (event.event === 'end') {
          ensureMsg()
          // 兜底：若全程没有 chunk（异常/空内容），此时才创建消息并补上标题
          if (pendingHeader) {
            const separator = messages.value[msgIdx].content ? '\n\n---\n\n' : ''
            messages.value[msgIdx].content += `${separator}${pendingHeader}`
            pendingHeader = ''
          }
          // 如果有思维导图图片，追加图片
          if (event.image_url) {
            const imgMarkdown = `\n\n![思维导图](${event.image_url})`
            messages.value[msgIdx].content += imgMarkdown
            typeImages[currentType] = event.image_url
          }
          if (event.raw_mermaid) {
            messages.value[msgIdx].content += `\n\n\`\`\`mermaid\n${event.raw_mermaid}\n\`\`\``
          }
          // 思维导图：后端直接输出 Markdown 大纲，保存供前端 markmap 渲染
          if (currentType === 'mindmap' && event.content) {
            messages.value[msgIdx].mindmapOutline = event.content
          }
          // 视频封面
          if (event.video_covers) {
            Object.assign(videoCovers, event.video_covers)
          }
          streamingText.value = `✅ ${RESOURCE_LABELS[currentType] || currentType} 生成完成`
        }

        // 全部完成
        if (event.event === 'complete') {
          ensureMsg()
          streamingText.value = ''
          // 流式结束：清掉展示用切片，正文回落到完整 content（由 ChatBubble 剥 JSON 显示）
          delete messages.value[msgIdx].displayContent
          messages.value[msgIdx].imageUrls = typeImages
          messages.value[msgIdx].videoCovers = videoCovers  // url→cover 映射

          // ✅ C 功能：生成完成后追加自然引导语，引导用户选择下一步
          if (singleType && NEXT_STEP_GUIDES[singleType]) {
            messages.value[msgIdx].content += `\n\n---\n\n> 💡 ${NEXT_STEP_GUIDES[singleType]}`
          }
        }
      })

      if (msgIdx !== -1 && !messages.value[msgIdx].content) {
        messages.value[msgIdx].content = '✅ 学习资源生成完成！请在右侧查看。'
      }
    } catch (err) {
      ensureMsg()
      messages.value[msgIdx].content = `❌ 资源生成失败: ${err.message}`
    }
  }

  // ========== 练习批改总结（无用户消息，直出报告） ==========
  async function sendExerciseSummary(topic, data) {
    loading.value = true
    streamingText.value = '正在生成批改报告...'

    const msgIdx = messages.value.length
    messages.value.push({
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      intent: 'tutor',
    })

    const exercises = data?.exercises || []
    const answers = data?.answers || {}

    // 构建统计摘要（给后备用）
    const total = data?.totalCount || exercises.length
    const correct = data?.correctCount || 0
    const wrong = data?.wrongCount || 0

    try {
      // 落库 AI 出题作答（尽力而为，幂等 upsert；失败不影响批改报告）
      try {
        await practiceApi.saveAiExercises(userId.value, topic, exercises, answers)
      } catch { /* 落库失败不阻断批改 */ }

      // 方式一：优先调用专用批改接口（SSE 流式）
      const resp = await fetch('http://127.0.0.1:8000/api/exercise/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_id: userId.value,
          topic,
          exercises: JSON.stringify(exercises),
          answers: JSON.stringify(answers),
          language: speechLanguage.value,
        }),
      })

      if (resp.ok) {
        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        let fullContent = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() || ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const payload = line.slice(6).trim()
            if (payload === '[DONE]') continue
            try {
              const evt = JSON.parse(payload)
              if (evt.chunk) {
                fullContent += evt.chunk
                messages.value[msgIdx].content = fullContent
              }
            } catch { /* skip */ }
          }
        }

        if (fullContent) return
        // 内容为空，降级到方式二
      }

      // 方式二：SSE 失败 → 用普通聊天接口（走 tutor 能力）
      const summaryPrompt = [
        `请对关于「${topic}」的练习进行批改总结。`,
        `答题情况：共 ${total} 题，正确 ${correct} 题，错误 ${wrong} 题。`,
        '',
        '请用 Markdown 格式输出以下内容：',
        '',
        '## 📊 练习批改报告',
        '',
        '### 总体评价',
        '- 得分：XX/100',
        '- 正确率：XX%',
        '- 总体评语',
        '',
        '### 逐题点评',
        '- 列出每道题的正确/错误情况',
        '',
        '### 薄弱知识点分析',
        '- 列出薄弱知识点及原因',
        '',
        '### 学习建议',
        '- 针对薄弱点的改进方法',
        '',
        '### 下一步学习计划',
        '- 具体可执行的学习行动',
      ].join('\n')

      const res = await chatApi.send(userId.value, summaryPrompt, sessionId.value, 'tutor', speechLanguage.value)
      const reply = res.reply || '✅ 批改报告生成完成'
      // 流式打字效果
      streamingText.value = ''
      for (let i = 0; i < reply.length; i++) {
        streamingText.value += reply[i]
        await new Promise(r => setTimeout(r, 15))
      }
      messages.value[msgIdx].content = reply
    } catch (err) {
      messages.value[msgIdx].content = `❌ 批改报告生成失败: ${err.message}`
    } finally {
      streamingText.value = ''
      loading.value = false
    }
  }

  // ========== 学习路径 ==========
  /** 从用户消息里提取规划主题：'帮我制定 Python 数据分析学习路径' → 'Python数据分析' */
  function extractPathTopic(text) {
    return (text || '')
      .replace(/[帮我请我们给]/g, '')
      .replace(/制定|规划|生成|定制|安排|计划/g, '')
      .replace(/学习路径|学习计划|路径规划|学习规划|路径/g, '')
      .replace(/[。，,.!?！？\s]/g, '')
      .trim()
  }

  // ========== 学习路径向导（聊天内交互：画像起步 → 提问补充 → 草案确认） ==========
  /** 发起点 → 推一条向导助手消息（intent:'path'）并调 start；向导状态随对话原地更新。
   *  opts = { dailyHours, cycle }：PathStartDialog 已问的时间投入，随请求带给后端。 */
  function pathStart(topic, opts = {}) {
    const t = (topic || '').trim()
    if (!t) return
    // 按钮发起时补一条自然用户消息；打字发起时最后一条已是用户消息，不重复
    const last = messages.value[messages.value.length - 1]
    if (!last || last.role !== 'user' || !last.content.includes('学习路径')) {
      messages.value.push({ role: 'user', content: `我想规划「${t}」的学习路径`, timestamp: Date.now() })
    }
    const wm = reactive({
      role: 'assistant',
      intent: 'path',
      content: '',
      pathWizard: { status: 'loading', topic: t, startOpts: opts },
      timestamp: Date.now(),
    })
    messages.value.push(wm)
    // 向导卡自带内联 loading，不走全局 loading（避免出现重复的生成中气泡）
    onlinePathApi.start(userId.value, t, opts)
      .then(res => applyPathRes(wm, res))
      .catch(err => { wm.pathWizard = { status: 'error', topic: t, startOpts: opts, error: err.message } })
  }

  /** 统一把后端返回落到向导卡状态：need_info → ask；ready_to_generate → 流式生成；带 path → draft；否则 → error */
  function applyPathRes(wm, res) {
    const topic = wm.pathWizard?.topic || ''
    const startOpts = wm.pathWizard?.startOpts || {}
    if (res && res.need_info) {
      wm.pathWizard = {
        status: 'ask',
        topic,
        startOpts,
        questions: res.questions || [],
        missingKeys: res.missing_keys || [],
        collected: res.collected || {},
        confirmSubject: res.confirm_subject || '',
      }
    } else if (res && res.ready_to_generate) {
      // 信息已够 → 走流式生成草案（后台执行，向导卡显示进度）
      pathGenerateStream(wm, res.topic || topic, res.collected || {}, '')
    } else if (res && res.path) {
      wm.pathWizard = { status: 'draft', topic, startOpts, draft: res.path, draftId: res.draft_id || '' }
    } else {
      wm.pathWizard = { status: 'error', topic, startOpts, error: res?.error || '路径规划失败，请稍后再试' }
    }
  }

  /** 流式生成路径草案：消费 SSE 进度事件，完成后原地替换成草案 */
  async function pathGenerateStream(wm, topic, collected, draftId = '') {
    const prev = { ...wm.pathWizard }
    wm.pathWizard = {
      ...prev,
      status: 'generating',
      topic,
      progress: '正在生成学习路径草案…',
    }
    try {
      const response = await onlinePathApi.draftStream(userId.value, topic, collected, draftId)
      await parseSSEStream(response, (evt) => {
        if (evt.event === 'progress') {
          wm.pathWizard = { ...wm.pathWizard, progress: evt.message }
        } else if (evt.event === 'complete') {
          const draft = evt.path || {}
          if (draftId && collected?.feedback) draft.revision_reason = collected.feedback
          wm.pathWizard = {
            status: 'draft',
            topic,
            startOpts: prev.startOpts || {},
            draft,
            draftId: evt.draft_id || draftId,
            revised: !!draftId,
          }
        } else if (evt.event === 'error') {
          wm.pathWizard = { ...prev, status: 'error', error: evt.message }
        }
      })
      // 流结束但没收到 complete → 兜底报错
      if (wm.pathWizard.status === 'generating') {
        wm.pathWizard = { ...prev, status: 'error', error: '路径生成失败，请重试' }
      }
    } catch (err) {
      wm.pathWizard = { ...prev, status: 'error', error: err.message }
    }
  }

  /** 用户作答 → 推用户气泡 + 向导卡原地更新 */
  async function pathAnswer(wm, answers, answerText) {
    if (!wm?.pathWizard) return
    messages.value.push({ role: 'user', content: answerText || '好的，这是我的补充信息', timestamp: Date.now() })
    const prev = { ...wm.pathWizard }
    wm.pathWizard = { ...prev, status: 'loading' }
    try {
      const res = await onlinePathApi.answers(userId.value, prev.topic, prev.collected, answers)
      applyPathRes(wm, res)
    } catch (err) {
      wm.pathWizard = { ...prev, status: 'error', error: err.message }
    }
  }

  /** 确认草案 → 存储 + 完成态 + 阶段摘要消息 */
  async function pathConfirm(wm) {
    if (!wm?.pathWizard) return
    messages.value.push({ role: 'user', content: '确认采用这条学习路径 ✅', timestamp: Date.now() })
    const prev = { ...wm.pathWizard }
    wm.pathWizard = { ...prev, status: 'loading' }
    try {
      const res = await onlinePathApi.confirm(userId.value, prev.draftId)
      if (res && res.ok) {
        wm.pathWizard = {
          status: 'done',
          topic: prev.topic,
          draft: res.path || prev.draft,
          draftId: res.draft_id || prev.draftId,
        }
        pushPathSavedMessage(res.path)
        // 路径已确认 → 刷新引导状态（path.done）
        fetchOnboarding()
      } else {
        wm.pathWizard = { ...prev, status: 'error', error: res?.error || '确认失败，请重试' }
      }
    } catch (err) {
      wm.pathWizard = { ...prev, status: 'error', error: err.message }
    }
  }

  /** 向导草案阶段：给某个节点加一条学习资源（返回的新草案节点原地合入，不触发重新生成） */
  async function pathAddDraftResource(wm, nodeId, title, url, platform = '') {
    if (!wm?.pathWizard) return false
    const prev = { ...wm.pathWizard }
    try {
      const res = await onlinePathApi.addDraftResource(
        userId.value, prev.draftId, nodeId, title.trim(), url.trim(), platform)
      if (res && res.ok && res.path) {
        wm.pathWizard = { ...prev, draft: res.path, status: 'draft' }
        return true
      }
      ElMessage.warning(res?.error || '添加资源失败，请重试')
      return false
    } catch (err) {
      ElMessage.warning(err.message || '添加资源失败')
      return false
    }
  }

  /** 修改草案 → 带 feedback 重新生成 */
  async function pathRevise(wm, feedback) {
    if (!wm?.pathWizard) return
    messages.value.push({ role: 'user', content: `修改意见：${feedback}`, timestamp: Date.now() })
    const prev = { ...wm.pathWizard }
    wm.pathWizard = { ...prev, status: 'loading' }
    try {
      const res = await onlinePathApi.confirm(userId.value, prev.draftId, feedback)
      if (res && res.ready_to_generate) {
        // 流式重新生成
        await pathGenerateStream(wm, res.topic || prev.topic, res.collected || {}, res.draft_id || prev.draftId)
      } else if (res && res.ok && res.revised && res.path) {
        wm.pathWizard = {
          status: 'draft',
          topic: prev.topic,
          draft: res.path || prev.draft,
          draftId: res.draft_id || prev.draftId,
          revised: true,
        }
      } else {
        wm.pathWizard = { ...prev, status: 'error', error: res?.error || '修改失败，请重试' }
      }
    } catch (err) {
      wm.pathWizard = { ...prev, status: 'error', error: err.message }
    }
  }

  /** 确认成功后留一条阶段摘要（供后续追问走 tutor） */
  function pushPathSavedMessage(path) {
    const stages = (path?.stages || []).map(s => `${s.title}（${s.estimated_days}天）`).join('、')
    const msg = [
      `## ✅ 已确认学习路径「${path?.path_name || ''}」`,
      path?.goal ? `${path.goal}` : '',
      path?.total_duration_days ? `**总周期**: ${path.total_duration_days} 天` : '',
      stages ? `**阶段**: ${stages}` : '',
      '',
      '去左侧「📒 我的练习」查看详细计划、打卡刷题吧！',
    ].filter(Boolean).join('\n')
    messages.value.push({
      role: 'assistant',
      content: msg,
      intent: 'plan',
      timestamp: Date.now(),
    })
  }

  // ========== 画像对话（多轮） ==========
  async function sendProfileChat(text) {
    // 如果没有 sessionId，走 init
    if (!sessionId.value) {
      try {
        const res = await profileApi.init(userId.value, userName.value, userGrade.value, userMajor.value, speechLanguage.value)
        sessionId.value = res.session_id || ('sess_' + Date.now())
        currentIntent.value = 'profile'

        streamingText.value = ''
        const reply = res.first_question || '你好！请告诉我你的学习情况～'
        for (let i = 0; i < reply.length; i++) {
          streamingText.value += reply[i]
          await new Promise(r => setTimeout(r, 15))
        }
        messages.value.push({ role: 'assistant', content: reply, timestamp: Date.now(), intent: 'profile' })
        return
      } catch (err) {
        messages.value.push({ role: 'assistant', content: '画像初始化失败: ' + err.message, isError: true, timestamp: Date.now() })
        return
      }
    }

    // 已有 session，走 chat
    try {
      const res = await profileApi.send(userId.value, sessionId.value, text, speechLanguage.value)
      currentIntent.value = 'profile'

      streamingText.value = ''
      const reply = res.reply || '继续说说你的情况吧～'
      for (let i = 0; i < reply.length; i++) {
        streamingText.value += reply[i]
        await new Promise(r => setTimeout(r, 15))
      }

      const msg = { role: 'assistant', content: reply, timestamp: Date.now(), intent: 'profile' }
      messages.value.push(msg)

      // 画像构建完成 → 刷新画像数据
      if (res.is_completed) {
        sessionId.value = ''  // 重置 session，下次重新开始
        currentIntent.value = ''
        fetchProfile()
      }
    } catch (err) {
      messages.value.push({ role: 'assistant', content: '对话失败: ' + err.message, isError: true, timestamp: Date.now() })
    }
  }

  // ========== 获取画像 ==========
  async function fetchProfile() {
    try {
      const p = await profileApi.get(userId.value)
      profile.value = p
      const r = await profileApi.radar(userId.value)
      radarData.value = r.dimensions || []
    } catch { /* 忽略 */ }
    // 画像可能刚完成采集 → 同步刷新引导状态
    fetchOnboarding()
  }

  // ========== 新手引导状态 ==========
  async function fetchOnboarding() {
    if (!userId.value) return
    try {
      onboarding.value = await onboardingApi.status(userId.value)
    } catch { /* 后端不可用时静默，引导条不显示 */ }
  }

  async function skipOnboarding(step) {
    if (!userId.value) return
    try {
      onboarding.value = await onboardingApi.skip(userId.value, step)
    } catch { /* 静默 */ }
  }

  // ========== 会话持久化（localStorage） ==========
  function saveMessages() {
    try {
      const key = `chat_history_${userId.value}_${sessionId.value}`
      localStorage.setItem(key, JSON.stringify(messages.value))
    } catch { /* localStorage 满时忽略 */ }
  }

  function loadMessages(sid) {
    try {
      const key = `chat_history_${userId.value}_${sid || sessionId.value}`
      const raw = localStorage.getItem(key)
      return raw ? JSON.parse(raw) : []
    } catch { return [] }
  }

  // 自动监听消息变化并持久化

  // ========== 重置 / 切换 ==========
  function resetChat() {
    // 切换前保存当前会话
    saveMessages()
    messages.value = []
    sessionId.value = 'sess_' + Date.now()
    // 新对话/切换用户 → 解绑上传文档，避免仍基于文档回答
    tempFileId.value = ''
    profile.value = null
    radarData.value = []
    resourceProgress.value = {}
    agentNodeMap.value = {}
  }

  async function switchUser(newUserId) {
    // 保存当前用户会话
    saveMessages()
    userId.value = newUserId
    resetChat()
    loadSessions()
    await fetchProfile()
    // 切换用户 → 重拉引导状态
    fetchOnboarding()
  }

  function switchSession(id) {
    // 保存当前会话
    saveMessages()
    sessionId.value = id
    // 加载目标会话历史
    messages.value = loadMessages(id)
    streamingText.value = ''
    window.speechSynthesis.cancel()
  }

  function newSession() {
    saveMessages()
    window.speechSynthesis.cancel()
    resetChat()
    // 更新会话标题 + 保存空历史占位
    const now = Date.now()
    const newSess = {
      id: sessionId.value,
      title: '新对话',
      time: '刚刚',
      timestamp: now,
    }
    sessions.value.unshift(newSess)
    saveMessages() // 存空数组占位
  }

  function removeSession(id) {
    const idx = sessions.value.findIndex(s => s.id === id)
    if (idx !== -1) sessions.value.splice(idx, 1)
    // 清除 localStorage 中的历史
    try {
      localStorage.removeItem(`chat_history_${userId.value}_${id}`)
    } catch {}
    if (sessionId.value === id) newSession()
  }

  // 主题切换
  function setTheme(newTheme) {
    theme.value = newTheme
    localStorage.setItem('theme', newTheme)
    document.documentElement.setAttribute('data-theme', newTheme === 'default' ? '' : newTheme)
  }

  // 语言切换
  function setLanguage(newLang) {
    language.value = newLang
    localStorage.setItem('language', newLang)
  }

  // 语音语言切换
  function setSpeechLanguage(newLang) {
    speechLanguage.value = newLang
    localStorage.setItem('speechLanguage', newLang)
    window.speechSynthesis.cancel()
  }

  // 修改密码
  function changePassword(oldPassword, newPassword) {
    const storedPassword = localStorage.getItem(`password_${userId.value}`)
    if (!storedPassword) {
      return { success: false, message: '该账号尚未设置密码，请先注册' }
    }
    if (storedPassword !== oldPassword) {
      return { success: false, message: '原密码不正确' }
    }
    if (newPassword.length < 6) {
      return { success: false, message: '新密码长度至少6位' }
    }
    localStorage.setItem(`password_${userId.value}`, newPassword)
    return { success: true, message: '密码修改成功' }
  }

  // 用户注销（彻底删除账号）
  function deleteAccount(password) {
    const storedPassword = localStorage.getItem(`password_${userId.value}`)
    if (!storedPassword) {
      return { success: false, message: '该账号尚未设置密码' }
    }
    if (storedPassword !== password) {
      return { success: false, message: '密码不正确' }
    }
    try {
      localStorage.removeItem(`password_${userId.value}`)
      localStorage.removeItem(`chat_sessions_${userId.value}`)
      for (const sess of sessions.value) {
        localStorage.removeItem(`chat_history_${userId.value}_${sess.id}`)
      }
    } catch {}
    logout()
    return { success: true, message: '账号已成功注销' }
  }

  // 会话列表持久化
  function saveSessions() {
    try {
      const key = `chat_sessions_${userId.value}`
      localStorage.setItem(key, JSON.stringify(sessions.value))
    } catch {}
  }

  // 自动持久化：消息变化时保存到 localStorage
  watch(messages, () => { saveMessages() }, { deep: true })
  // 自动持久化：会话列表变化时保存到 localStorage
  watch(sessions, () => { saveSessions() }, { deep: true })

  // 刷新会话时间显示
  function refreshSessionTimes() {
    if (!sessions.value || !Array.isArray(sessions.value)) return
    for (const sess of sessions.value) {
      if (sess.timestamp) {
        sess.time = formatTime(sess.timestamp)
      }
    }
  }

  // 初始化主题
  setTheme(theme.value)
  // 刷新会话时间显示
  refreshSessionTimes()

  return {
    messages, loading, sessionId, userId, userName, userGrade, userMajor, agentNodeMap,
    profile, radarData, streamingText, resourceProgress,
    sessions, sidebarCollapsed, usernameDisplay, currentIntent, pathWizardRequest,
    theme, language, themeOptions, languageOptions, currentLocale, getLocale,
    speechLanguage, speechLanguageOptions,
    isLoggedIn,
    onboarding, fetchOnboarding, skipOnboarding,
    tempFileId, fileUploading, uploadedFiles,
    setTempFileId, setFileUploading, addUploadedFile, addSystemMessage,
    sendMessage, sendExerciseSummary, sendKbChat, fetchProfile, fetchAssistantIntro, resetChat, switchUser,
    switchSession, newSession, removeSession,
    setTheme, setLanguage, setSpeechLanguage,
    changePassword, deleteAccount,
    login, quickLogin, logout,
    pathStart, pathAnswer, pathConfirm, pathRevise, pathAddDraftResource,
  }
})
