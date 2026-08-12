/**
 * 页面用动态信息（如知识库名）覆盖顶栏面包屑；组件卸载自动还原为
 * route.meta.crumb。传入 ref/computed，值为 undefined 时不覆盖。
 */
import type { Ref } from 'vue'
import { onUnmounted, watch } from 'vue'
import { useAppStore } from '@/store/modules/app'

export function useCrumb(crumb: Ref<string | undefined>) {
  const appStore = useAppStore()
  watch(crumb, (v) => {
    appStore.crumbOverride = v ?? ''
  }, { immediate: true })
  onUnmounted(() => {
    appStore.crumbOverride = ''
  })
}
