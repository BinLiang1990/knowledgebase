/**
 * 知识库分类树（PRD §4.11，issue #39/#40；字段镜像
 * backend/src/kb_backend/schemas/category.py::CategoryOut）。
 *
 * 列表为全量扁平返回（分类规模数百条内不分页），树形组装与子树合计
 * 由前端完成——后端只给每个节点「直属的启用中知识库数」。
 */
import { request } from '@/utils/request'

export interface Category {
  id: number
  parent_id: number | null
  name: string
  sort_order: number
  /** 直属的启用中知识库数（不含子孙，不含已停用——PRD §4.11 计数口径） */
  active_knowledge_base_count: number
  /** 直属的全部状态知识库数（删除拦截口径：含已停用与回收站，占用即阻塞） */
  total_knowledge_base_count: number
  created_at: string
  updated_at: string
}

/** 拖拽落点：before/after = 插入为目标的前/后同级，inside = 挂为目标的子分类 */
export type CategoryMovePosition = 'before' | 'after' | 'inside'

/**
 * 分类树的选中范围（CategoryTree 发给列表页的过滤口径）：
 * 「全部」/「未分类」是虚拟节点；选中真实分类时 ids 已含全部子孙
 * （PRD §4.11：按分类过滤固定含子孙）。
 */
export type CategoryScope
  = | { type: 'all' }
    | { type: 'none' }
    | { type: 'category', id: number, label: string, ids: number[] }

export interface CategoryInput {
  name: string
  /** null/省略 = 顶级分类 */
  parent_id?: number | null
}

/** 全量扁平列表，已按 (sort_order, id) 排序 */
export function listCategories() {
  return request.get<Category[]>('/categories')
}

export function createCategory(input: CategoryInput) {
  return request.post<Category>('/categories', input)
}

/** 改名 / 换父分类（换父级 = 移动节点，排到新同级末尾，子树整体随迁） */
export function updateCategory(id: number, input: Partial<CategoryInput>) {
  return request.patch<Category>(`/categories/${id}`, input)
}

/** 仅允许删除空分类（无子分类且无知识库归属，含已停用的）；非空后端报 400 */
export function deleteCategory(id: number) {
  return request.delete<Record<string, never>>(`/categories/${id}`)
}

/** 拖拽移动：成环/落点重名由后端校验，失败整体不生效 */
export function moveCategory(id: number, input: { target_id: number, position: CategoryMovePosition }) {
  return request.post<Category>(`/categories/${id}/move`, input)
}
