/**
 * 页面级取数的统一小工具：loading/error/data 三件套 + 手动/被动重载。
 * 替代 React 版的 TanStack Query——本应用页面挂载即取全量数据、无跨页缓存
 * 诉求，一个带竞态防护的加载器就够了，不值得引入完整的查询缓存层。
 * 错误提示已由 utils/request.ts 拦截器统一弹出，这里只保留布尔态供页面
 * 渲染「加载失败/重试」块。
 */
import type { WatchSource } from 'vue'
import { ref, shallowRef, watch } from 'vue'

export interface UseAsyncDataOptions {
  /** 创建时立即加载（默认 true）；false 用于「展开时才取数」类场景 */
  immediate?: boolean
  /** 这些源变化时自动重载（等价于 React Query 把参数放进 query key） */
  watch?: WatchSource[]
  /** 返回 false 时 load() 直接跳过——用于「知识库确认有效后才发请求」的门禁 */
  enabled?: () => boolean
}

export function useAsyncData<T>(fetcher: () => Promise<T>, options: UseAsyncDataOptions = {}) {
  const { immediate = true, watch: sources, enabled } = options
  const data = shallowRef<T | undefined>(undefined)
  const loading = ref(false)
  const error = ref(false)

  // 竞态防护：参数连续变化触发多个在途请求时，只有最后一个的结果落地，
  // 先发后至的旧响应不能覆盖新响应（React Query 靠 key 隔离，这里靠序号）。
  let seq = 0

  async function load() {
    if (enabled && !enabled())
      return
    const current = ++seq
    loading.value = true
    error.value = false
    try {
      const result = await fetcher()
      if (current !== seq)
        return
      data.value = result
    }
    catch {
      // 错误提示已由 request 拦截器统一弹出，这里只记录状态
      if (current === seq)
        error.value = true
    }
    finally {
      if (current === seq)
        loading.value = false
    }
  }

  if (sources?.length)
    watch(sources, () => load())
  if (immediate)
    load()

  return { data, loading, error, load }
}
