<script setup lang="ts">
// 操作日志页：跨全部知识库的答案变更流水（issue #14）。
import { listGlobalChangeLog } from '@/api/changeLog'
import { useAsyncData } from '@/composables/useAsyncData'

defineOptions({ name: 'OperationLog' })

const logQuery = useAsyncData(listGlobalChangeLog)
</script>

<template>
  <div class="notice">
    跨全部知识库的答案变更流水：写答案 / 改答案 / 撤回答案，每一步都留痕，不可物理删除。「操作」列可以直接对仍然生效的答案执行撤回。
  </div>

  <div class="card ov">
    <div class="card-head">
      <span class="tick" />
      <h3>全量变更留痕</h3>
      <span class="sub">每个知识库、每个知识点、每次撤回，都可在此追溯</span>
    </div>

    <div v-if="logQuery.loading.value" class="empty-block">
      <span class="spin" /> 加载中…
    </div>
    <div v-else-if="logQuery.error.value" class="empty-block">
      加载失败，请检查网络或后端服务后
      <br>
      <a @click="logQuery.load">重试</a>
    </div>
    <ChangeLogTable
      v-else
      :entries="logQuery.data.value ?? []"
      show-location
      @refresh="logQuery.load"
    />
  </div>
</template>
