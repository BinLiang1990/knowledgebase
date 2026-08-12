/**
 * 跨模块通用的接口契约类型（前端开发规范 §7.2.3）。
 * 全局口径：本系统后端主键是自增 int（远小于 2^53），id 一律 number；
 * 唯一可能超出 JS 安全整数范围的是 number 型维度坐标值（uint64，见
 * docs/PRD.md coord.py 一节），utils/request.ts 的 json-bigint 解析会把
 * 超范围整数保留为字符串，所以坐标值类型始终是 string | number | boolean。
 */

/** 后端统一响应包（docs/PRD.md §4.10） */
export interface ApiResult<T> {
  code: number
  data: T
  msg: string
}
