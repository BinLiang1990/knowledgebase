<script setup lang="ts">
// 只放真实存在页面的两个 tab——demo 的 kb-tabs 还有「回收站」，但该页面
// 从未被建出且无 issue 跟踪；一个点了 404 的 tab 比不显示更糟（issue #13）。
type KbTabKey = 'kp-list' | 'settings'

const props = defineProps<{
  kbId: number
  active: KbTabKey
}>()

const TABS: Array<[KbTabKey, string]> = [
  ['kp-list', '知识点列表'],
  ['settings', '知识库设置'],
]

function linkFor(key: KbTabKey): string {
  return key === 'kp-list'
    ? `/knowledge-bases/${props.kbId}/knowledge-points`
    : `/knowledge-bases/${props.kbId}/settings`
}
</script>

<template>
  <div class="tabs kb-tabs">
    <RouterLink
      v-for="[key, label] in TABS"
      :key="key"
      :to="linkFor(key)"
      class="tab"
      :class="{ active: key === active }"
    >
      {{ label }}
    </RouterLink>
  </div>
</template>
