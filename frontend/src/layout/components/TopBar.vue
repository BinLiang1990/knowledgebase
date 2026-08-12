<script setup lang="ts">
import { useAppStore } from '@/store/modules/app'

const route = useRoute()
const appStore = useAppStore()

const now = ref(new Date())
// 定时器统一 useIntervalFn，随组件销毁自动清理（规范 §8.5）
useIntervalFn(() => {
  now.value = new Date()
}, 1000)

// 页面可用 useCrumb 注入知识库名等动态信息，否则回退路由静态 crumb
const crumb = computed(() => appStore.crumbOverride || route.meta.crumb || '')
</script>

<template>
  <header class="top">
    <span class="h-bar" />
    <h1>{{ route.meta.title }}</h1>
    <span class="crumb">{{ crumb }}</span>
    <span class="spacer" />
    <span class="top-badge">已接入真实后端</span>
    <div class="top-clock">
      <div class="t num">
        {{ now.toLocaleTimeString('zh-CN', { hour12: false }) }}
      </div>
      <div class="d">
        {{ now.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) }}
      </div>
    </div>
    <div class="top-avatar">
      AD
    </div>
  </header>
</template>
