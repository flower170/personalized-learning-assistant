/**
 * Markdown 渲染工具：统一完成「解析 → 代码高亮 → 安全消毒」
 * 依赖：markdown-it（解析）+ highlight.js（代码高亮）+ dompurify（XSS 过滤）
 */
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'
import 'highlight.js/styles/github.css'

// mermaid 相关语言 → 输出 <pre class="mermaid-block">，供 ChatBubble 后续用 mermaid 渲染成图
const MERMAID_LANGS = [
  'mermaid', 'graph', 'flowchart', 'sequence', 'sequencediagram', 'statediagram',
  'classdiagram', 'erdiagram', 'gantt', 'pie', 'journey', 'gitgraph', 'timeline',
  'blockbeta', 'quadrantchart',
]

const md = new MarkdownIt({
  html: false,      // 禁用原始 HTML，只渲染 Markdown（安全第一，配合 DOMPurify 双保险）
  breaks: true,     // 单个换行符也渲染为 <br>，选项/题目分行显示
  linkify: true,    // 自动识别链接
})

// 自定义 fence 规则：mermaid 语言块输出 pre.mermaid-block；其余做 highlight.js 语法高亮
md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const lang = (token.info || '').trim().toLowerCase().replace(/_/g, '')
  const code = token.content || ''

  if (lang === 'mermaid' || MERMAID_LANGS.includes(lang)) {
    return `<pre class="mermaid-block"><code class="language-mermaid">${md.utils.escapeHtml(code)}</code></pre>\n`
  }

  let highlighted = ''
  if (lang && hljs.getLanguage(lang)) {
    try {
      highlighted = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
    } catch {
      highlighted = ''
    }
  }

  const cls = lang ? `hljs language-${md.utils.escapeHtml(lang)}` : 'hljs'
  return `<pre><code class="${cls}">${highlighted || md.utils.escapeHtml(code)}</code></pre>\n`
}

/**
 * 将大模型用【CODE_BEGIN:lang】...【CODE_END】包裹的代码块转换为 markdown 围栏代码块。
 * 包裹标记仅用于程序识别，转换后不再显示在页面上，交给 markdown-it 渲染成代码块。
 */
function wrapCodeMarkers(text) {
  return String(text).replace(
    /【CODE_BEGIN:(\w+)】\s*\n([\s\S]*?)\n?【CODE_END】/g,
    (_, lang, code) => `\`\`\`${lang}\n${code.trimEnd()}\n\`\`\``,
  )
}

/**
 * 渲染 Markdown 为安全的 HTML（已完成语法高亮 + XSS 消毒）
 * @param {string} text Markdown 源文本
 * @returns {string} 消毒后的 HTML
 */
export function renderMarkdown(text) {
  if (!text) return ''
  try {
    const pre = wrapCodeMarkers(String(text))
    return DOMPurify.sanitize(md.render(pre))
  } catch {
    return String(text)
  }
}

export { MERMAID_LANGS }
