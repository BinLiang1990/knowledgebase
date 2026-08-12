<script setup lang="ts">
// 按维度字段类型渲染取值输入——number/date 靠原生 input 类型把关有效性，
// boolean 是固定下拉（提交侧仍需 toFilterValue 做类型转换，见 utils/dimension.ts）。
// ConditionPicker、CoordEditor、维度管理页共用，转换规则不允许再出现第二份拷贝。
import type { Dimension } from '@/api/dimension'

withDefaults(defineProps<{
  dim: Dimension
  /**
   * 现有调用方（筛选条件、答案条件）渲染本组件时字段必已加入条件，没有
   * 「未设置」态，boolean 分支可以把空值展示为「是」。维度管理页的
   * 「默认取值提示」是真正可为空的——展示上静默默认成「是」而底层状态
   * （与实际提交值）仍为空，会「看着选了、存的却不是」。allowUnset 提供
   * 真实的「未设置」选项并停止空值强制展示为 true，不影响未传它的调用方
   * （Codex 结论，PR #29）。
   */
  allowUnset?: boolean
}>(), { allowUnset: false })

const model = defineModel<string>({ required: true })

function onBooleanChange(event: Event) {
  model.value = (event.target as HTMLSelectElement).value
}
</script>

<template>
  <input v-if="dim.field_type === 'number'" v-model="model" type="number">
  <input v-else-if="dim.field_type === 'date'" v-model="model" type="date">
  <select
    v-else-if="dim.field_type === 'boolean'"
    :value="allowUnset ? model : model || 'true'"
    @change="onBooleanChange"
  >
    <option v-if="allowUnset" value="">
      未设置
    </option>
    <option value="true">
      是
    </option>
    <option value="false">
      否
    </option>
  </select>
  <input v-else v-model="model" type="text" placeholder="输入取值">
</template>
