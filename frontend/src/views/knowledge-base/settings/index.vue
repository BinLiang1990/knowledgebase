<script setup lang="ts">
// 知识库设置页：从全局维度库勾选本知识库启用的维度。
// 勾选状态是「从服务端种子化一次、之后本地独占」的表单状态——React 版为绕
// TanStack Query 的缓存/后台刷新竞态写了三个 effect + ref（PR #29 第 3/4 轮），
// Vue 版没有查询缓存，挂载即取、取到即种，只剩「每个 kbId 种一次」这一条规则。
import { listAdminDimensions, listEnabledDimensions, setEnabledDimensions } from '@/api/dimension'
import { listKnowledgeBases } from '@/api/knowledgeBase'
import { useAsyncData } from '@/composables/useAsyncData'
import { useCrumb } from '@/composables/useCrumb'
import { FIELD_TYPE_LABEL } from '@/utils/dimension'
import KbTabs from '../components/KbTabs.vue'

defineOptions({ name: 'KnowledgeBaseSettings' })

const route = useRoute()
const kbId = computed(() => Number(route.params.kbId))
const kbIdValid = computed(() => Number.isFinite(kbId.value))

const kbQuery = useAsyncData(listKnowledgeBases)
const kb = computed(() => kbQuery.data.value?.find(k => k.id === kbId.value))
const kbReady = computed(() => kb.value?.status === 'active')

useCrumb(computed(() => (kb.value ? `${kb.value.name} / 知识库设置` : undefined)))

const adminDimensionsQuery = useAsyncData(listAdminDimensions)
const enabledDimensionsQuery = useAsyncData(() => listEnabledDimensions(kbId.value), {
  enabled: () => kbReady.value,
  watch: [kbReady],
})

const checkedKeys = ref<Set<string> | null>(null)
const saving = ref(false)

// 路由 :kbId 变到另一个库不会重挂载本组件（还是同一条匹配路由）——不重置的话
// 会拿着上一个库的勾选状态看（并保存到）另一个库（Codex 结论，PR #29 第 3 轮）
watch(kbId, () => {
  checkedKeys.value = null
  enabledDimensionsQuery.load()
})

// 每个 kbId 只从服务端种子化一次；之后的勾选完全由用户own，保存触发的任何
// 重取都不得覆盖用户已点的状态
watch(enabledDimensionsQuery.data, (data) => {
  if (checkedKeys.value === null && data)
    checkedKeys.value = new Set(data.map(d => d.key))
})

// save() 也要用它过滤：页面开着时别人可能全局停用了某维度，重取后该维度的
// 复选框直接消失，而 checkedKeys 没人自动清理——不过滤的话保存会整体被后端
// 拒绝（「已停用，无法启用」），用户却没有复选框可取消（Codex，PR #29 第 6 轮）
const activeDimensions = computed(() =>
  (adminDimensionsQuery.data.value ?? []).filter(d => d.status === 'active'),
)

const dataIsError = computed(() => adminDimensionsQuery.error.value || enabledDimensionsQuery.error.value)
// checkedKeys === null 只在底层请求仍可能成功时才算加载中——请求已失败则
// 永远种不上，再当加载态会让页面卡在没有重试入口的转圈上（Codex，PR #29）
const dataLoading = computed(() =>
  adminDimensionsQuery.loading.value
  || enabledDimensionsQuery.loading.value
  || (checkedKeys.value === null && !dataIsError.value),
)

function toggle(key: string) {
  const next = new Set(checkedKeys.value)
  if (next.has(key))
    next.delete(key)
  else
    next.add(key)
  checkedKeys.value = next
}

function retryData() {
  adminDimensionsQuery.load()
  enabledDimensionsQuery.load()
}

async function save() {
  const activeKeys = new Set(activeDimensions.value.map(d => d.key))
  const keysToSubmit = Array.from(checkedKeys.value ?? []).filter(key => activeKeys.has(key))
  saving.value = true
  try {
    await setEnabledDimensions(kbId.value, keysToSubmit)
    ElMessage.success('已保存本知识库启用的维度')
  }
  catch {
    // 服务端错误已由 request 拦截器统一提示
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <template v-if="kbQuery.loading.value">
    <KbTabs v-if="kbIdValid" :kb-id="kbId" active="settings" />
    <div class="card">
      <div class="empty-block">
        <span class="spin" /> 加载中…
      </div>
    </div>
  </template>

  <template v-else-if="kbQuery.error.value">
    <KbTabs v-if="kbIdValid" :kb-id="kbId" active="settings" />
    <div class="card">
      <div class="empty-block">
        加载知识库失败，请稍后重试
        <br>
        <span style="display: inline-block; margin-top: 12px">
          <a @click="kbQuery.load">重试</a>
        </span>
      </div>
    </div>
  </template>

  <template v-else-if="!kb || kb.status !== 'active'">
    <div class="card">
      <div class="empty-block">
        没有指定有效的知识库（可能已被停用或不存在）
        <br>
        <span style="display: inline-block; margin-top: 12px">
          <RouterLink class="btn primary" to="/knowledge-bases">‹ 返回知识库列表</RouterLink>
        </span>
      </div>
    </div>
  </template>

  <template v-else>
    <KbTabs :kb-id="kbId" active="settings" />

    <div class="notice">
      维度定义是<b>全局共享</b>的，但每个知识库需要单独勾选「启用」才能在写答案时用到该维度作为适用条件；停用/取消勾选不影响本知识库历史答案里已经写入的取值，只影响之后能否继续选用。
    </div>

    <div class="card ov">
      <div class="card-head">
        <span class="tick" />
        <h3>启用维度</h3>
        <span class="sub">从全局维度库中，选择本知识库「{{ kb.name }}」要用到的维度</span>
        <span class="spacer" />
        <span class="ops">
          <RouterLink to="/dimensions">前往维度管理 »</RouterLink>
        </span>
      </div>

      <div v-if="dataLoading" class="empty-block">
        <span class="spin" /> 加载中…
      </div>
      <div v-else-if="dataIsError" class="empty-block">
        加载失败，请检查网络或后端服务后<a @click="retryData"> 重试</a>
      </div>
      <div v-else-if="activeDimensions.length === 0" class="empty-block">
        还没有任何启用中的全局维度，先去<RouterLink to="/dimensions">
          「维度管理」
        </RouterLink>新增一个。
      </div>
      <div v-else>
        <label
          v-for="dim in activeDimensions"
          :key="dim.key"
          class="chk"
          style="width: 100%; justify-content: space-between; margin-bottom: 8px"
        >
          <span style="display: flex; align-items: center; gap: 10px">
            <input type="checkbox" :checked="checkedKeys?.has(dim.key) ?? false" @change="toggle(dim.key)">
            <span style="font-weight: 600; color: var(--ink-1)">{{ dim.label }}</span>
            <span class="tag blue ftype-tag">{{ FIELD_TYPE_LABEL[dim.field_type] }}</span>
            <span class="field-hint">权重 {{ dim.weight }}</span>
          </span>
          <span class="field-hint">全局共 {{ dim.answer_count }} 条答案在用</span>
        </label>
      </div>

      <div class="form-row" style="margin-top: 6px">
        <!-- dataIsError 也必须禁用保存：失败态下 checkedKeys 仍是 null，此时
             保存会提交空维度集合，静默清光本知识库已启用的全部维度（Codex，
             PR #29 第 2 轮） -->
        <button
          type="button"
          class="btn primary"
          :disabled="dataLoading || dataIsError || saving"
          @click="save"
        >
          保 存
        </button>
      </div>
    </div>
  </template>
</template>
