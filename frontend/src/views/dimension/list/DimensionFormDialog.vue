<script setup lang="ts">
// 新增/编辑维度合体弹窗：open() 新增、open(dim) 编辑。
// 字段类型创建后不可修改（编辑态禁用）；key 由 label 生成且不可变。
import type { AdminDimension, Dimension } from '@/api/dimension'
import { createDimension, updateDimension } from '@/api/dimension'
import { FIELD_TYPE_LABEL } from '@/utils/dimension'

const emit = defineEmits<{
  /** 保存成功——父页面重载维度列表 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const target = ref<AdminDimension | null>(null)
const label = ref('')
const fieldType = ref<Dimension['field_type']>('text')
const weight = ref('50')
const defaultValue = ref('')
const error = ref('')

const isEdit = computed(() => target.value !== null)
const title = computed(() => (isEdit.value ? `编辑维度 · ${target.value!.label}` : '新增维度'))

function open(dim?: AdminDimension) {
  target.value = dim ?? null
  label.value = dim?.label ?? ''
  fieldType.value = dim?.field_type ?? 'text'
  weight.value = dim ? String(dim.weight) : '50'
  // 编辑态的 default_value 可能是 null——「原本是 null」与「原本是空串」在
  // 这里都折叠成 ''，没问题：两者提交回去都是 null（issue #13 设计 §4.2）
  defaultValue.value = dim?.default_value ?? ''
  error.value = ''
  visible.value = true
}
defineExpose({ open })

function onFieldTypeChange(event: Event) {
  // 换类型时连同默认取值提示一起重置——为旧类型输入的值（如文本 "hello"）
  // 对新类型（如时间）通常不合法，但 default_value 两端都是无跨类型校验的
  // 纯字符串，不清空会在新类型输入框显示为空的同时把旧值静默提交上去
  // （Codex 结论，PR #29 第 2 轮）；只在新增态可达，编辑态本下拉已禁用
  fieldType.value = (event.target as HTMLSelectElement).value as Dimension['field_type']
  defaultValue.value = ''
}

async function submit() {
  const trimmedLabel = label.value.trim()
  if (!trimmedLabel) {
    error.value = '请填写维度名称。'
    return
  }
  // 编辑态也刻意比后端严：保持 label 与已生成的 key 不在视觉上分道扬镳，
  // 尽管 DimensionUpdate 本身没有 "/" 检查（key 编辑时不变，没有路由风险，
  // issue #13 设计 §4.3）
  if (trimmedLabel.includes('/')) {
    error.value = '名称不能包含斜杠(/)'
    return
  }
  error.value = ''

  const trimmedDefaultValue = defaultValue.value.trim()
  // null 而非 undefined——整个省略 default_value 键对后端意味着「保持不变」，
  // 与显式 null（清空）语义不同（issue #13 设计 §4.2）
  const submittedDefaultValue = trimmedDefaultValue === '' ? null : trimmedDefaultValue
  // 不能写 `parseInt(...) || 50`：0 是假值，真实输入的 "0" 会静默跳到 50
  // 而不是被夹取到 1。先解析、仅对真 NaN 回退 50、再夹取（Kimi 终审，PR #29）
  const parsedWeight = Number.parseInt(weight.value, 10)
  const clampedWeight = Math.min(100, Math.max(1, Number.isNaN(parsedWeight) ? 50 : parsedWeight))

  submitting.value = true
  try {
    if (target.value) {
      await updateDimension(target.value.key, {
        label: trimmedLabel,
        weight: clampedWeight,
        default_value: submittedDefaultValue,
      })
      ElMessage.success(`已更新维度「${trimmedLabel}」`)
    }
    else {
      await createDimension({
        label: trimmedLabel,
        field_type: fieldType.value,
        weight: clampedWeight,
        default_value: submittedDefaultValue,
      })
      ElMessage.success(`已新增维度「${trimmedLabel}」，需要到「知识库设置」里为具体知识库启用后才能使用`)
    }
    visible.value = false
    emit('success')
  }
  catch {
    // 服务端错误已由 request 拦截器统一提示，保持弹窗打开供修改
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" :title="title" width="560px" :close-on-click-modal="false">
    <div class="mf">
      <label><span class="req">*</span>维度名称</label>
      <!-- 新增限 100（该值同时成为 key，String(100) 列，设计 §4.1）；编辑限 255，
           对应 DimensionUpdate 里 label 自己的 max_length——key 编辑时不变，
           不再是约束（Kimi 终审，PR #29） -->
      <input
        v-model="label"
        type="text"
        placeholder="例如：部门 / 标签 / 复核周期"
        :maxlength="isEdit ? 255 : 100"
      >
      <div class="hint">
        {{ isEdit
          ? `key「${target!.key}」创建后不可修改；字段类型「${FIELD_TYPE_LABEL[target!.field_type]}」创建后不可修改。`
          : '新增时会同时作为内部标识(key)；创建后 key 不可更改，显示名称之后仍可修改。' }}
      </div>
    </div>
    <div class="mf">
      <label><span class="req">*</span>字段类型</label>
      <select :value="fieldType" :disabled="isEdit" @change="onFieldTypeChange">
        <option value="text">
          文本
        </option>
        <option value="number">
          数值
        </option>
        <option value="date">
          时间
        </option>
        <option value="boolean">
          布尔
        </option>
      </select>
      <div class="hint">
        创建后不可修改，用于答案条件的取值输入校验。
      </div>
    </div>
    <div class="mf">
      <label><span class="req">*</span>权重(1–100)</label>
      <input v-model="weight" type="number" min="1" max="100">
      <div class="hint">
        两条答案条件同样具体、又都没有精确命中查询时，涉及维度的权重总和更高的答案优先返回。
      </div>
    </div>
    <div class="mf">
      <label>默认取值提示(可选)</label>
      <ValueInput
        v-model="defaultValue"
        :dim="{ key: '', label: '', weight: 0, field_type: fieldType }"
        allow-unset
      />
      <div class="hint">
        仅作为「写答案」时该维度输入框的预填提示，不做强制校验。
      </div>
    </div>
    <p v-if="error" class="hint" style="color: var(--red)">
      {{ error }}
    </p>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn primary" :disabled="submitting" @click="submit">
        确 定
      </button>
    </template>
  </el-dialog>
</template>
