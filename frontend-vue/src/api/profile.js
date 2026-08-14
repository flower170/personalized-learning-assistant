/**
 * 画像 API 模块
 * 与后端 ProfileCapability 接口对接
 */
import http from './index'

const BASE = '/api/profile'

/**
 * 发送画像对话消息
 * @param {string} studentId
 * @param {string} message
 * @returns {Promise<{response: string, session_id: string}>}
 */
export async function chat(studentId, message) {
  // 使用 /api/profile/chat/send 端点
  const { data } = await http.post('/profile/chat/send', {
    student_id: studentId,
    message,
    session_id: '',  // 后端自动查找活跃会话
  })
  return {
    response: data.reply || data.first_question || '好的',
    session_id: data.session_id || '',
  }
}

/**
 * 获取画像 6 维度收集进度
 * @param {string} studentId
 * @returns {Promise<{dim_list: Array, finished_count: number, total: number, progress_percent: string}>}
 */
export async function getProgress(studentId) {
  try {
    const { data } = await http.get(`/profile/${studentId}/radar`)
    const dims = data.dimensions || []
    const total = 6
    const finished = dims.filter(d => d.score > 0).length
    return {
      dim_list: dims.map(d => ({
        name: d.name,
        collected: d.score > 0,
        score: d.score,
        description: d.description,
      })),
      finished_count: finished,
      total,
      progress_percent: `${Math.round((finished / total) * 100)}%`,
    }
  } catch {
    return {
      dim_list: [],
      finished_count: 0,
      total: 6,
      progress_percent: '0%',
    }
  }
}

/**
 * 获取画像对话进度（含当前阶段）
 * @param {string} studentId
 */
export async function getChatProgress(studentId) {
  const { data } = await http.get(`/profile/${studentId}/progress`)
  return data
}

/**
 * 重置画像
 * @param {string} studentId
 */
export async function resetProfile(studentId) {
  const { data } = await http.post('/profile/reset', null, {
    params: { student_id: studentId },
  })
  return data
}

/**
 * 增量更新画像信息
 * @param {string} studentId
 * @param {object} updates - 需要更新的字段
 */
export async function updateProfile(studentId, updates) {
  const { data } = await http.post('/profile/update_increment', {
    student_id: studentId,
    updates,
  })
  return data
}
