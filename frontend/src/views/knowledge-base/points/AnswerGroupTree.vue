<script setup lang="ts">
// 行展开后的答案树（只读概览）：默认答案 / 单维度取值 / 组合条件 三段。
// 已整链撤回的条件组不展示——知识点列表是「看现在什么在生效」的地方，
// 不是审计轨迹；撤回历史去变更留痕/版本历史看。
import type { Dimension } from '@/api/dimension'
import type { AnswerGroup } from '@/api/knowledgePoint'

const props = defineProps<{
  groups: AnswerGroup[]
  dimensions: Dimension[]
}>()

// coord key 已不在启用维度列表（全局停用或本库禁用）时按原 key 展示——
// 维度停用后历史数据保持可见是预期行为（PRD §6 规则 7），不是错误态
function labelFor(key: string): string {
  return props.dimensions.find(d => d.key === key)?.label ?? key
}

const liveGroups = computed(() => props.groups.filter(g => !g.revoked))

const defaultGroups = computed(() => liveGroups.value.filter(g => Object.keys(g.coord).length === 0))

const singleByKey = computed(() => {
  const map = new Map<string, AnswerGroup[]>()
  for (const g of liveGroups.value) {
    const keys = Object.keys(g.coord)
    if (keys.length === 1)
      map.set(keys[0], [...(map.get(keys[0]) ?? []), g])
  }
  return map
})

const multiGroups = computed(() => liveGroups.value.filter(g => Object.keys(g.coord).length >= 2))
</script>

<template>
  <div v-if="!liveGroups.length" class="kids">
    <div class="mini-note" style="padding: 8px 0">
      还没有任何答案
    </div>
  </div>
  <div v-else class="kids">
    <template v-if="defaultGroups.length > 0">
      <div class="tnode" style="cursor: default">
        ▾ <span class="tag gray">默认答案</span>
      </div>
      <div class="kids">
        <!-- 未生效与已撤回是两回事（设计文档 §2）：demo 混为一谈，这里是有意修正 -->
        <div
          v-for="g in defaultGroups"
          :key="g.latest_answer.id"
          class="tnode"
          :style="g.live_answer ? 'cursor: default' : 'cursor: default; color: var(--ink-6)'"
        >
          ·
          <template v-if="g.live_answer">
            {{ g.live_answer.content }}
            <span class="cnt"><span class="num" style="font-weight: 400">{{ g.live_answer.effective_time }}</span> 起 · 共 {{ g.version_count }} 版</span>
          </template>
          <template v-else>
            {{ g.latest_answer.content }}
            <span class="cnt"><span class="num" style="font-weight: 400">{{ g.latest_answer.effective_time }}</span> 起生效 · 尚未生效</span>
          </template>
        </div>
      </div>
    </template>

    <div v-for="[key, groupsForKey] in singleByKey" :key="key">
      <div class="tnode" style="cursor: default">
        ▾ <span class="tag purple">{{ labelFor(key) }}</span>
        <span class="cnt">{{ groupsForKey.length }} 个取值</span>
      </div>
      <div class="kids">
        <div
          v-for="g in groupsForKey"
          :key="g.latest_answer.id"
          class="tnode"
          :style="g.live_answer ? 'cursor: default' : 'cursor: default; color: var(--ink-6)'"
        >
          <span class="tag blue">{{ String(g.coord[key]) }}</span>
          <span style="color: var(--ink-6)">→</span>
          <template v-if="g.live_answer">
            {{ g.live_answer.content }}
            <span class="cnt"><span class="num" style="font-weight: 400">{{ g.live_answer.effective_time }}</span> 起 · 共 {{ g.version_count }} 版</span>
          </template>
          <template v-else>
            {{ g.latest_answer.content }}
            <span class="cnt"><span class="num" style="font-weight: 400">{{ g.latest_answer.effective_time }}</span> 起生效 · 尚未生效</span>
          </template>
        </div>
      </div>
    </div>

    <template v-if="multiGroups.length > 0">
      <div class="tnode" style="cursor: default">
        ▾ <span class="tag purple">组合条件</span>
        <span class="cnt">{{ multiGroups.length }} 条</span>
      </div>
      <div class="kids">
        <div
          v-for="g in multiGroups"
          :key="g.latest_answer.id"
          class="tnode"
          :style="g.live_answer ? 'cursor: default' : 'cursor: default; color: var(--ink-6)'"
        >
          <span v-for="(value, key) in g.coord" :key="key" class="tag blue">
            {{ labelFor(String(key)) }} = {{ String(value) }}
          </span>
          <span style="color: var(--ink-6)">→</span>
          <template v-if="g.live_answer">
            {{ g.live_answer.content }}
            <span class="cnt"><span class="num" style="font-weight: 400">{{ g.live_answer.effective_time }}</span> 起 · 共 {{ g.version_count }} 版</span>
          </template>
          <template v-else>
            {{ g.latest_answer.content }}
            <span class="cnt"><span class="num" style="font-weight: 400">{{ g.latest_answer.effective_time }}</span> 起生效 · 尚未生效</span>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>
