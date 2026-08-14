import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120000 })

// ======================== 1. 统一聊天 API ========================

export const chatApi = {
  /** LangGraph 编排聊天 */
  send: async (userId, message, sessionId = '', explicitType = '', language = '', tempFileId = '') => {
    const { data } = await http.post('/chat/send', {
      student_id: userId, message, session_id: sessionId, explicit_type: explicitType, language,
      temp_file_id: tempFileId || undefined,
    })
    return data
  },

  /** SSE 流式聊天（GET 方式） */
  sendStream: (userId, message, sessionId = '', explicitType = '', language = '') => {
    const params = new URLSearchParams({
      student_id: userId, message, session_id: sessionId, explicit_type: explicitType, language,
    })
    return new EventSource(`/api/chat/stream?${params}`)
  },
}

// ======================== 2. 画像 API ========================

export const profileApi = {
  /** 获取完整画像 */
  get: async (userId) => {
    const { data } = await http.get(`/profile/${userId}`)
    return data
  },

  /** 获取雷达图 */
  radar: async (userId) => {
    const { data } = await http.get(`/profile/${userId}/radar`)
    return data
  },

  /** 初始化画像对话 */
  init: async (userId, name, grade, major, language = '') => {
    const { data } = await http.post('/profile/chat/init', {
      student_id: userId, name, grade, major, language,
    })
    return data
  },

  /** 发送画像对话消息 */
  send: async (studentId, sessionId, message, language = '') => {
    const { data } = await http.post('/profile/chat/send', {
      student_id: studentId, session_id: sessionId, message, language,
    })
    return data
  },

  /** 增量更新画像信息 */
  updateProfile: async (studentId, updates) => {
    const { data } = await http.post('/profile/update_increment', {
      student_id: studentId,
      updates,
    })
    return data
  },
}

// ======================== 3. 资源生成 API ========================

export const resourceApi = {
  /** 多智能体协同生成（SSE 流式） */
  dispatch: (userId, topic, resourceTypes, course = '', demand = '', tempFileId = '') => {
    return http.post('/dispatch/generate', {
      student_id: userId, topic,
      resource_types: resourceTypes,
      course, user_demand: demand,
      temp_file_id: tempFileId || undefined,
    })
  },

  /** 生成全部5种资源（SSE 流式） */
  dispatchAll: (userId, topic, course = '', demand = '') => {
    return http.post('/dispatch/generate-all', {
      student_id: userId, topic, course, user_demand: demand,
    })
  },
}

// ======================== 4. 学习路径 API ========================

export const planApi = {
  /** 生成学习路径 */
  generate: async (userId, topic, goal = '', days = 30, minutes = 60, language = '') => {
    const { data } = await http.post('/plan/generate', {
      student_id: userId, topic, goal, total_days: days, daily_minutes: minutes, language,
    })
    return data
  },

  /** 获取学习路径及进度 */
  get: async (userId) => {
    const { data } = await http.get(`/learning-path/${userId}`)
    return data
  },
}

// ======================== 5. 智能辅导 API ========================

export const tutorApi = {
  /** 智能辅导流式答疑 */
  ask: (userId, question, history = []) => {
    return http.post('/tutor/ask', {
      student_id: userId, question, conversation_history: history,
    })
  },
}

// ======================== 6. 练习交互 API ========================

export const exerciseApi = {
  /** 修改练习题（SSE 流式） */
  modify: (userId, topic, exercises, feedback = '') => {
    return http.post('/exercise/modify', {
      student_id: userId, topic,
      exercises: JSON.stringify(exercises),
      feedback,
    })
  },

  /** 总结练习情况并建议下一步（SSE 流式） */
  summarize: (userId, topic, exercises, answers = {}, language = '') => {
    return http.post('/exercise/summarize', {
      student_id: userId, topic,
      exercises: JSON.stringify(exercises),
      answers: JSON.stringify(answers),
      language,
    })
  },
}

// ======================== 7. 报告 API ========================

export const reportApi = {
  /** 获取完整学习报告数据 */
  generate: async (userId) => {
    const [profile, radar, learningPath] = await Promise.allSettled([
      profileApi.get(userId),
      profileApi.radar(userId),
      planApi.get(userId),
    ])

    const chatHistory = []
    try {
      const sessions = JSON.parse(localStorage.getItem(`chat_sessions_${userId}`) || '[]')
      for (const sess of sessions) {
        const msgs = JSON.parse(localStorage.getItem(`chat_history_${userId}_${sess.id}`) || '[]')
        if (msgs.length > 0) {
          chatHistory.push({
            sessionId: sess.id,
            title: sess.title,
            time: sess.time,
            messageCount: msgs.length,
            lastMessage: msgs[msgs.length - 1]?.content?.slice(0, 50) + '...',
          })
        }
      }
    } catch {
      // ignore localStorage errors
    }

    return {
      profile: profile.status === 'fulfilled' ? profile.value : null,
      radar: radar.status === 'fulfilled' ? radar.value : null,
      learningPath: learningPath.status === 'fulfilled' ? learningPath.value : null,
      chatHistory: chatHistory.slice(0, 10),
      generatedAt: new Date().toLocaleString('zh-CN'),
    }
  },
}

// ======================== 8. 学习路径 API（交互式：画像起步 → 提问补充 → 草案确认） ========================

export const onlinePathApi = {
  /** Stage 1: 发起路径规划（画像+联网） */
  start: async (studentId, topic) => {
    const { data } = await http.post('/online-path/start', { student_id: studentId, topic })
    return data
  },

  /** Stage 2: 补全信息 */
  answers: async (studentId, topic, collected, answers) => {
    const { data } = await http.post('/online-path/answers', {
      student_id: studentId, topic, collected, answers,
    })
    return data
  },

  /** Stage 3: 直接出草案 */
  generate: async (studentId, topic, collected = {}) => {
    const { data } = await http.post('/online-path/generate', {
      student_id: studentId, topic, collected,
    })
    return data
  },

  /** 确认 / 带 feedback 修改 */
  confirm: async (studentId, draftId, feedback = '') => {
    const { data } = await http.post('/online-path/confirm', {
      student_id: studentId, draft_id: draftId, feedback,
    })
    return data
  },

  /** 已确认路径 + 进度 */
  get: async (studentId) => {
    const { data } = await http.get(`/online-path/${studentId}`)
    return data
  },
}

// ======================== 9. 练习卡 API ========================

export const practiceApi = {
  /** 用户选「深入练习」：按知识点搜官方 OJ 练习卡 */
  deepSearch: async (studentId, nodeId, topic, knowledgePoint, options = {}) => {
    const { data } = await http.post('/practice/deep-search', {
      student_id: studentId, node_id: nodeId, topic, knowledge_point: knowledgePoint,
      platforms: options.platforms, count: options.count, max_results: options.max_results,
    })
    return data
  },

  /** 某节点练习卡 */
  cards: async (studentId, nodeId) => {
    const { data } = await http.get('/practice/cards', { params: { student_id: studentId, node_id: nodeId } })
    return data
  },

  /** 更新练习卡状态/答案/笔记 */
  update: async (studentId, cardId, fields) => {
    const { data } = await http.post('/practice/update', {
      student_id: studentId, card_id: cardId, fields,
    })
    return data
  },

  /** 打卡 */
  checkin: async (studentId, nodeId, note = '') => {
    const { data } = await http.post('/practice/checkin', {
      student_id: studentId, node_id: nodeId, note,
    })
    return data
  },

  /** 进度 + 激励数据 */
  progress: async (studentId) => {
    const { data } = await http.get(`/practice/progress/${studentId}`)
    return data
  },

  /** 聊天 AI 出题作答落库（幂等）→ 进「我的练习」统计与错题集 */
  saveAiExercises: async (studentId, topic, exercises, answers) => {
    const { data } = await http.post('/practice/save-ai-exercises', {
      student_id: studentId, topic,
      exercises: JSON.stringify(exercises || []), answers: JSON.stringify(answers || {}),
    })
    return data
  },

  /** 错题集：OJ 错题（全量）+ AI 错题（全量） */
  wrongQuestions: async (studentId) => {
    const { data } = await http.get('/practice/wrong-questions', { params: { student_id: studentId } })
    return data
  },

  /** AI 错题重做：服务端重判 */
  redoAiExercise: async (studentId, exerciseId, userAnswer) => {
    const { data } = await http.post('/practice/redo-ai-exercise', {
      student_id: studentId, exercise_id: exerciseId, user_answer: userAnswer,
    })
    return data
  },

  /** 我的题目：全部命名题目集（含题目/题型/作答状态） */
  listCollections: async (studentId) => {
    const { data } = await http.get('/practice/collections', { params: { student_id: studentId } })
    return data
  },

  /** 新建命名题目集 */
  createCollection: async (studentId, name) => {
    const { data } = await http.post('/practice/collections/create', { student_id: studentId, name })
    return data
  },

  /** 收藏一题到题目集 */
  addToCollection: async (studentId, collectionId, topic, exercise) => {
    const { data } = await http.post('/practice/collections/add', {
      student_id: studentId, collection_id: collectionId, topic, exercise,
    })
    return data
  },

  /** 题目集内重做（服务端重判） */
  redoCollectionQuestion: async (studentId, collectionId, questionId, userAnswer) => {
    const { data } = await http.post('/practice/collections/redo', {
      student_id: studentId, collection_id: collectionId, question_id: questionId, user_answer: userAnswer,
    })
    return data
  },

  /** 从题目集移除一题 */
  removeCollectionQuestion: async (studentId, collectionId, questionId) => {
    const { data } = await http.post('/practice/collections/remove-question', {
      student_id: studentId, collection_id: collectionId, question_id: questionId,
    })
    return data
  },

  /** 删除整个题目集 */
  deleteCollection: async (studentId, collectionId) => {
    const { data } = await http.post('/practice/collections/delete', {
      student_id: studentId, collection_id: collectionId,
    })
    return data
  },

  /** 外部平台学习打卡（自评，呼应路径） */
  nodeStudy: async (studentId, nodeId, fields) => {
    const { data } = await http.post('/practice/node-study', {
      student_id: studentId, node_id: nodeId, ...fields,
    })
    return data
  },
}

// ======================== 10. 新手引导 API ========================

export const onboardingApi = {
  /** 引导状态（画像/路径完成度 + current_step + all_done） */
  status: async (studentId) => {
    const { data } = await http.get(`/onboarding/${studentId}`)
    return data
  },

  /** 标记某步跳过（profile/path） */
  skip: async (studentId, step) => {
    const { data } = await http.post('/onboarding/skip', { student_id: studentId, step })
    return data
  },
}

// ======================== 11. 技能差距 API ========================

export const skillGapApi = {
  /** 技能 vs 市场需求差距分析 */
  analyze: async (studentId, role = '后端开发工程师', topK = 6) => {
    const { data } = await http.post('/skill-gap/analyze', {
      student_id: studentId, role, top_k: topK,
    })
    return data
  },
}

// ======================== 7. 系统 API ========================

export const systemApi = {
  /** 获取可用模型列表 */
  models: async () => {
    const { data } = await http.get('/models')
    return data
  },

  /** 获取能力清单 */
  capabilities: async () => {
    const { data } = await http.get('/capabilities')
    return data
  },

  /** 获取 AI 自我介绍和能力说明（带服务端缓存） */
  assistantIntro: async () => {
    const { data } = await http.get('/assistant/intro')
    return data
  },

  /** 健康检查 */
  health: async () => {
    const { data } = await http.get('/health')
    return data
  },
}

export default http
