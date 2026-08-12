/**
 * 日期格式化统一收口（前端开发规范 §11.2）：同一语义只留一个函数，
 * 全项目不允许出现两个行为不同的同名格式化函数。
 */
import dayjs from 'dayjs'

/**
 * 本地时区的今天（YYYY-MM-DD）。不能用 toISOString()——它报告的是 UTC 日历日，
 * 在 UTC+8 的每天前 8 小时会比本地日期落后一天（Codex 评审结论，PR #23）。
 */
export function today(): string {
  return dayjs().format('YYYY-MM-DD')
}

/** ISO 时间串取日期部分（YYYY-MM-DD）；后端时间字段都是 ISO 格式，裁剪即可 */
export function formatDate(iso: string): string {
  return iso.slice(0, 10)
}

/** ISO 时间串转「YYYY-MM-DD HH:mm:ss」展示格式 */
export function formatDateTime(iso: string): string {
  return iso.replace('T', ' ').slice(0, 19)
}
