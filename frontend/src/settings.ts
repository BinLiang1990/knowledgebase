/**
 * 全局协议常量（前端开发规范 §12.1）。
 * 本系统无登录/权限体系（数据可见范围由后端决定，规范 §10.5），
 * 故没有 TOKEN_KEY / X-App-Type 一节的常量。
 */

/** 后端统一响应包成功码（docs/PRD.md §4.10：code 200 成功、444 业务/校验错误） */
export const API_SUCCESS_CODE = 200

/** 请求超时（毫秒）——防止挂起的请求永不 resolve（PR #22 评审结论，随 axios 迁移保留） */
export const REQUEST_TIMEOUT_MS = 10_000
