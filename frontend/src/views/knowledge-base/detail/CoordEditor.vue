<script setup lang="ts">
import type { CoordRow } from './coordRows'
// 写/编辑答案表单的「适用条件」多行编辑器——与 ConditionPicker（查询用，
// 一次锁一个条件）不同，这里编辑答案钉住的全部 0~N 个条件（设计文档 §4.2）。
import type { Dimension } from '@/api/dimension'

const props = defineProps<{
  dimensions: Dimension[]
}>()

const rows = defineModel<CoordRow[]>({ required: true })

function addRow() {
  rows.value = [...rows.value, { key: '', raw: '' }]
}
function removeRow(index: number) {
  rows.value = rows.value.filter((_, i) => i !== index)
}
function updateRow(index: number, patch: Partial<CoordRow>) {
  rows.value = rows.value.map((r, i) => (i === index ? { ...r, ...patch } : r))
}

// 已被其他行选走的维度不再出现在本行下拉——demo 允许同一维度出现两次并静默
// 只保留最后一行的值；设计文档 §4.2 视之为应当阻止的歧义而非照搬
function availableDims(index: number) {
  const row = rows.value[index]
  const usedByOtherRows = rows.value.filter((_, j) => j !== index).map(r => r.key)
  return props.dimensions.filter(d => d.key === row.key || !usedByOtherRows.includes(d.key))
}

function dimFor(row: CoordRow) {
  return props.dimensions.find(d => d.key === row.key)
}

function onDimChange(index: number, event: Event) {
  const key = (event.target as HTMLSelectElement).value
  const nextDim = props.dimensions.find(d => d.key === key)
  // 与 ConditionPicker 同源的修复：boolean <select> 总会显示一个选中项
  // （浏览器画不出「什么都没选」），背后的状态必须与视觉显示同步起步
  updateRow(index, { key, raw: nextDim?.field_type === 'boolean' ? 'true' : '' })
}
</script>

<template>
  <div>
    <template v-for="(row, i) in rows" :key="row.locked !== undefined ? `locked-${row.key}` : `row-${i}`">
      <div v-if="row.locked !== undefined" class="form-row" style="margin-bottom: 8px">
        <span class="tag gray">{{ row.key }}（已停用）</span>
        <span class="hint">{{ String(row.locked) }}</span>
      </div>
      <div v-else class="form-row" style="margin-bottom: 8px">
        <select :value="row.key" style="min-width: 120px" @change="onDimChange(i, $event)">
          <option value="">
            选择维度…
          </option>
          <option v-for="d in availableDims(i)" :key="d.key" :value="d.key">
            {{ d.label }}
          </option>
        </select>
        <span class="f-val-wrap">
          <ValueInput
            v-if="dimFor(row)"
            :dim="dimFor(row)!"
            :model-value="row.raw"
            @update:model-value="(v: string) => updateRow(i, { raw: v })"
          />
          <input v-else type="text" disabled placeholder="先选维度">
        </span>
        <a class="danger" style="font-size: 13px" @click="removeRow(i)">移除</a>
      </div>
    </template>
    <button type="button" class="btn sm" style="margin-top: 8px" @click="addRow">
      + 加一个条件
    </button>
    <div class="hint">
      维度只能从本知识库已启用的维度中选择；条件不变 = 同组追加新版本，条件改了 = 迁移到新条件组
    </div>
  </div>
</template>
