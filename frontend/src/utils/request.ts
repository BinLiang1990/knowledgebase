/**
 * axios 单例（前端开发规范 §7.1）。所有后端调用只会看到两种结果：
 * 解包后的业务 data，或被拦截器统一弹过错误提示后 reject 的 ApiError——
 * 页面永远不用自己 catch 弹提示，只写 try/finally 管 loading。
 */
import type { AxiosRequestConfig } from 'axios'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import JSONBigInt from 'json-bigint'
import { API_SUCCESS_CODE, REQUEST_TIMEOUT_MS } from '@/settings'

// 探测/轮询等确需静默的请求可传 silent: true（通过模块增强合法化，不做强转）
declare module 'axios' {
  interface AxiosRequestConfig {
    silent?: boolean
  }
}

/** 业务/网络错误统一异常类型；message 已是可直接展示的中文文案 */
export class ApiError extends Error {}

// storeAsString：超出 Number 安全范围的整数（如 uint64 维度坐标值）保留为
// 精度不丢失的字符串——原生 JSON.parse 会把 9007199254740993 静默舍入。
// 这是历史 React 版 apiClient 已知且接受的缺陷（CoordEditor 注释记录的
// out-of-scope 限制），随本次迁移一并修复。
const parser = JSONBigInt({ storeAsString: true })

const service = axios.create({
  baseURL: import.meta.env.VITE_APP_BASE_API,
  timeout: REQUEST_TIMEOUT_MS,
  transformResponse: [
    (data: unknown) => {
      if (typeof data !== 'string' || data === '')
        return data
      try {
        return parser.parse(data)
      }
      catch {
        // 非 JSON 响应体（文件流、纯文本错误页等）原样返回
        return data
      }
    },
  ],
})

service.interceptors.response.use(
  (response) => {
    const res = response.data
    // 无 code 字段（文件流等）原样返回
    if (res === null || typeof res !== 'object' || !('code' in res))
      return res
    if (res.code === API_SUCCESS_CODE)
      return res.data
    const msg: string = res.msg || '操作失败'
    if (!response.config.silent)
      ElMessage.error(msg)
    return Promise.reject(new ApiError(msg))
  },
  (error) => {
    // 网络失败、CORS、超时/中断等——没有响应包可解，统一一句话
    const msg = '网络异常，请稍后重试'
    if (!error?.config?.silent)
      ElMessage.error(msg)
    return Promise.reject(new ApiError(msg))
  },
)

/** 泛型薄壳：T 即拦截器解包后的业务数据类型（规范 §7.1.5） */
export const request = {
  get: <T>(url: string, config?: AxiosRequestConfig) =>
    service.get(url, config) as Promise<T>,
  post: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    service.post(url, data, config) as Promise<T>,
  put: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    service.put(url, data, config) as Promise<T>,
  patch: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    service.patch(url, data, config) as Promise<T>,
  delete: <T>(url: string, config?: AxiosRequestConfig) =>
    service.delete(url, config) as Promise<T>,
}

export default service
