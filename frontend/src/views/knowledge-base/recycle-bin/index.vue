<script setup lang="ts">
// 知识库回收站：已删除（未彻底删除）的知识库列表，支持还原与彻底删除。
// 「彻底删除」后端实现仍为软删（数据保留在库里），但界面上不可再还原。
import type { KnowledgeBaseRecycleItem } from '@/api/knowledgeBase'
import { listRecycleBin, purgeKnowledgeBase, restoreKnowledgeBase } from '@/api/knowledgeBase'
import { useAsyncData } from '@/composables/useAsyncData'
import { formatDateTime } from '@/utils/format'

defineOptions({ name: 'KnowledgeBaseRecycleBin' })

const binQuery = useAsyncData(listRecycleBin)

const confirmVisible = ref(false)
const submitting = ref(false)
const action = ref<'restore' | 'purge'>('restore')
const target = ref<KnowledgeBaseRecycleItem | null>(null)

function openConfirm(kb: KnowledgeBaseRecycleItem, next: 'restore' | 'purge') {
  target.value = kb
  action.value = next
  confirmVisible.value = true
}

async function confirm() {
  if (!target.value)
    return
  submitting.value = true
  try {
    if (action.value === 'restore') {
      await restoreKnowledgeBase(target.value.id)
      ElMessage.success('已还原，知识库当前为「已停用」状态')
    }
    else {
      await purgeKnowledgeBase(target.value.id)
      ElMessage.success('已彻底删除')
    }
    binQuery.load()
  }
  catch {
    // 错误提示由请求拦截器统一弹出
  }
  finally {
    submitting.value = false
    confirmVisible.value = false
  }
}
</script>

<template>
  <div class="notice">
    <b>回收站</b>存放已删除的知识库（仅已停用的知识库可被删除）。<b>还原</b>后知识库回到「已停用」状态，可再手动启用；<b>彻底删除</b>后不可再还原。回收站内的知识库仍占用名称，新建同名知识库会被拒绝。
  </div>

  <div class="card ov">
    <div class="card-head">
      <span class="tick" />
      <h3>知识库回收站</h3>
      <span class="spacer" />
      <span class="ops">
        <RouterLink to="/knowledge-bases" class="btn">
          返回知识库列表
        </RouterLink>
      </span>
    </div>

    <table class="tbl">
      <thead>
        <tr>
          <th>名称</th>
          <th>描述</th>
          <th>分类</th>
          <th>知识点数</th>
          <th>删除时间</th>
          <th>删除人</th>
          <th class="op-col">
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="binQuery.loading.value">
          <td colspan="7" class="empty">
            <span class="spin" /> 加载中…
          </td>
        </tr>
        <tr v-else-if="binQuery.error.value">
          <td colspan="7" class="empty">
            加载失败，请检查网络或后端服务后<a @click="binQuery.load"> 重试</a>
          </td>
        </tr>
        <tr v-else-if="(binQuery.data.value ?? []).length === 0">
          <td colspan="7" class="empty">
            回收站为空
          </td>
        </tr>
        <template v-else>
          <tr v-for="kb in binQuery.data.value" :key="kb.id">
            <td>{{ kb.name }}</td>
            <td>{{ kb.description || '—' }}</td>
            <td>
              <span v-if="kb.category_name" class="cat-tag">{{ kb.category_name }}</span>
              <span v-else class="cat-tag none">未分类</span>
            </td>
            <td class="num" style="font-weight: 400">
              {{ kb.active_knowledge_point_count }}
            </td>
            <td class="num" style="font-weight: 400">
              {{ formatDateTime(kb.deleted_at) }}
            </td>
            <td>{{ kb.deleted_by || '—' }}</td>
            <td class="op-col ops">
              <a @click="openConfirm(kb, 'restore')">还原</a>
              <a class="danger" @click="openConfirm(kb, 'purge')">彻底删除</a>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>

  <el-dialog
    v-model="confirmVisible"
    class="app-dialog"
    :title="action === 'restore' ? '还原知识库' : '彻底删除知识库'"
    width="560px"
    :close-on-click-modal="false"
  >
    <p style="font-size: 13.5px; color: var(--ink-2); line-height: 1.8;">
      即将{{ action === 'restore' ? '还原' : '彻底删除' }}知识库 <b style="color: var(--ink-1)">{{ target?.name }}</b>。
    </p>
    <div v-if="action === 'restore'" class="risk">
      还原后知识库回到「已停用」状态，列表中可见；如需继续使用，请在知识库列表中手动启用。
    </div>
    <div v-else class="risk">
      彻底删除后该知识库将从回收站消失，<b>不可再还原</b>。
    </div>
    <template #footer>
      <button type="button" class="btn" @click="confirmVisible = false">
        取 消
      </button>
      <button
        type="button"
        class="btn"
        :class="action === 'restore' ? 'primary' : 'danger'"
        :disabled="submitting"
        @click="confirm"
      >
        确 定
      </button>
    </template>
  </el-dialog>
</template>

<style scoped>
.cat-tag {
  display: inline-block;
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--gray-bg, #f5f8fd);
  border: 1px solid var(--gray-bd, #dde5f1);
  color: var(--ink-3);
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}
.cat-tag.none {
  color: var(--ink-5);
  border-style: dashed;
}
</style>
