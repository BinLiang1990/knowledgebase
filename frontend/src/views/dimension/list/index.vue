<script setup lang="ts">
// 维度管理页：全局维度定义的增改与启停。
import type { AdminDimension } from '@/api/dimension'
import { listAdminDimensions } from '@/api/dimension'
import { useAsyncData } from '@/composables/useAsyncData'
import { FIELD_TYPE_LABEL } from '@/utils/dimension'
import DimensionFormDialog from './DimensionFormDialog.vue'
import ToggleDimensionStatusDialog from './ToggleDimensionStatusDialog.vue'

defineOptions({ name: 'DimensionList' })

const dimensionsQuery = useAsyncData(listAdminDimensions)
const dimensions = computed(() => dimensionsQuery.data.value ?? [])

const formDialogRef = ref<InstanceType<typeof DimensionFormDialog>>()
const toggleDialogRef = ref<InstanceType<typeof ToggleDimensionStatusDialog>>()

function openCreate() {
  formDialogRef.value?.open()
}
function openEdit(dim: AdminDimension) {
  formDialogRef.value?.open(dim)
}
function openToggle(dim: AdminDimension) {
  toggleDialogRef.value?.open(dim)
}
</script>

<template>
  <div class="notice">
    维度的<b>字段类型</b>创建后不可修改（避免破坏已有数据的类型一致性）；如需变更类型，请停用旧维度并新建一个新维度。停用维度不影响历史答案已经写入的取值，只影响之后新增/编辑答案时是否还能选用它。每个知识库需要在「知识库设置」里单独<b>启用</b>想用的维度，才能在该知识库的答案里使用。<b>权重</b>用于查询条件没有精确命中时的回退排序：条件更具体的答案优先；同样具体时，涉及维度的权重总和更高的答案优先。
  </div>

  <div class="card ov">
    <div class="card-head">
      <span class="tick" />
      <h3>维度定义</h3>
      <span class="sub">知识点答案可携带的可扩展条件</span>
      <span class="spacer" />
      <span class="ops">
        <button type="button" class="btn primary" @click="openCreate">+ 新增维度</button>
      </span>
    </div>

    <table class="tbl">
      <thead>
        <tr>
          <th>key</th>
          <th>显示名称</th>
          <th>字段类型</th>
          <th>权重</th>
          <th>状态</th>
          <th>使用中的答案</th>
          <th class="op-col">
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="dimensionsQuery.loading.value">
          <td colspan="7" class="empty">
            <span class="spin" /> 加载中…
          </td>
        </tr>
        <tr v-else-if="dimensionsQuery.error.value">
          <td colspan="7" class="empty">
            加载失败，请检查网络或后端服务后<a @click="dimensionsQuery.load"> 重试</a>
          </td>
        </tr>
        <tr v-else-if="dimensions.length === 0">
          <td colspan="7" class="empty">
            暂无维度定义，点击右上角「+ 新增维度」创建
          </td>
        </tr>
        <template v-else>
          <tr v-for="dim in dimensions" :key="dim.key">
            <td class="num" style="font-weight: 400">
              {{ dim.key }}
            </td>
            <td>{{ dim.label }}</td>
            <td><span class="tag blue ftype-tag">{{ FIELD_TYPE_LABEL[dim.field_type] }}</span></td>
            <td class="num" style="font-weight: 400">
              {{ dim.weight }}
            </td>
            <td>
              <span v-if="dim.status === 'active'" class="status-dot ok"><i />启用中</span>
              <span v-else class="status-dot off"><i />已停用</span>
            </td>
            <td class="num" style="font-weight: 400">
              {{ dim.answer_count }}
            </td>
            <td class="op-col ops">
              <a @click="openEdit(dim)">编辑</a>
              <a :class="{ danger: dim.status === 'active' }" @click="openToggle(dim)">
                {{ dim.status === 'active' ? '停用' : '启用' }}
              </a>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>

  <DimensionFormDialog ref="formDialogRef" @success="dimensionsQuery.load" />
  <ToggleDimensionStatusDialog ref="toggleDialogRef" @success="dimensionsQuery.load" />
</template>
