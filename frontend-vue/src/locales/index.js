import zhCN from './zh-CN'
import enUS from './en-US'

export const messages = {
  'zh-CN': zhCN,
  'en-US': enUS,
}

export const languageOptions = [
  { value: 'zh-CN', label: '中文' },
  { value: 'en-US', label: 'English' },
]

export function getLanguageLabel(code) {
  const opt = languageOptions.find(o => o.value === code)
  return opt ? opt.label : code
}