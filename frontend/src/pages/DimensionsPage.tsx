import { useState } from 'react';
import {
  useAdminDimensions,
  useCreateDimension,
  useSetDimensionStatus,
  useUpdateDimension,
  type AdminDimension,
  type Dimension,
} from '../api/dimensions';
import { ApiError } from '../api/client';
import { AppShell } from '../components/layout/AppShell';
import { Modal } from '../components/ui/Modal';
import { ValueInput } from '../components/ui/dimensionValue';
import { useToast } from '../components/ui/Toast';

const FIELD_TYPE_LABEL: Record<Dimension['field_type'], string> = {
  text: '文本',
  number: '数值',
  date: '时间',
  boolean: '布尔',
};

export function DimensionsPage() {
  const { data: dimensions, isLoading, isError, refetch } = useAdminDimensions();
  const [formTarget, setFormTarget] = useState<AdminDimension | 'create' | null>(null);
  const [toggleTarget, setToggleTarget] = useState<AdminDimension | null>(null);

  return (
    <AppShell title="维度管理" crumb="知识库管理 / 维度管理">
      <div className="notice">
        维度的<b>字段类型</b>创建后不可修改（避免破坏已有数据的类型一致性）；如需变更类型，请停用旧维度并新建一个新维度。停用维度不影响历史答案已经写入的取值，只影响之后新增/编辑答案时是否还能选用它。每个知识库需要在「知识库设置」里单独<b>启用</b>想用的维度，才能在该知识库的答案里使用。<b>权重</b>用于查询条件没有精确命中时的回退排序：条件更具体的答案优先；同样具体时，涉及维度的权重总和更高的答案优先。
      </div>

      <div className="card ov">
        <div className="card-head">
          <span className="tick" />
          <h3>维度定义</h3>
          <span className="sub">知识点答案可携带的可扩展条件</span>
          <span className="spacer" />
          <span className="ops">
            <button type="button" className="btn primary" onClick={() => setFormTarget('create')}>
              + 新增维度
            </button>
          </span>
        </div>

        <table className="tbl">
          <thead>
            <tr>
              <th>key</th>
              <th>显示名称</th>
              <th>字段类型</th>
              <th>权重</th>
              <th>状态</th>
              <th>使用中的答案</th>
              <th className="op-col">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={7} className="empty">
                  <span className="spin" /> 加载中…
                </td>
              </tr>
            )}
            {isError && !isLoading && (
              <tr>
                <td colSpan={7} className="empty">
                  加载失败，请检查网络或后端服务后
                  <a onClick={() => refetch()}> 重试</a>
                </td>
              </tr>
            )}
            {!isLoading && !isError && (dimensions?.length ?? 0) === 0 && (
              <tr>
                <td colSpan={7} className="empty">
                  暂无维度定义，点击右上角「+ 新增维度」创建
                </td>
              </tr>
            )}
            {!isLoading &&
              !isError &&
              dimensions?.map((dim) => (
                <tr key={dim.key}>
                  <td className="num" style={{ fontWeight: 400 }}>
                    {dim.key}
                  </td>
                  <td>{dim.label}</td>
                  <td>
                    <span className="tag blue ftype-tag">{FIELD_TYPE_LABEL[dim.field_type]}</span>
                  </td>
                  <td className="num" style={{ fontWeight: 400 }}>
                    {dim.weight}
                  </td>
                  <td>
                    {dim.status === 'active' ? (
                      <span className="status-dot ok">
                        <i />
                        启用中
                      </span>
                    ) : (
                      <span className="status-dot off">
                        <i />
                        已停用
                      </span>
                    )}
                  </td>
                  <td className="num" style={{ fontWeight: 400 }}>
                    {dim.answer_count}
                  </td>
                  <td className="op-col ops">
                    <a onClick={() => setFormTarget(dim)}>编辑</a>
                    <a className={dim.status === 'active' ? 'danger' : ''} onClick={() => setToggleTarget(dim)}>
                      {dim.status === 'active' ? '停用' : '启用'}
                    </a>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {formTarget !== null && <DimensionFormModal target={formTarget} onClose={() => setFormTarget(null)} />}
      {toggleTarget !== null && (
        <ToggleDimensionStatusModal target={toggleTarget} onClose={() => setToggleTarget(null)} />
      )}
    </AppShell>
  );
}

function DimensionFormModal({
  target,
  onClose,
}: {
  target: AdminDimension | 'create';
  onClose: () => void;
}) {
  const isEdit = target !== 'create';
  const [label, setLabel] = useState(isEdit ? target.label : '');
  const [fieldType, setFieldType] = useState<Dimension['field_type']>(isEdit ? target.field_type : 'text');
  const [weight, setWeight] = useState(isEdit ? String(target.weight) : '50');
  // isEdit's target.default_value may be null — both "was null" and "was
  // an empty string" collapse to '' here, which is fine: both submit back
  // as null (§4.2, issue #13 design doc), so there is no distinction worth
  // preserving through this round-trip.
  const [defaultValue, setDefaultValue] = useState(isEdit ? target.default_value ?? '' : '');
  const [error, setError] = useState('');
  const createMutation = useCreateDimension();
  const updateMutation = useUpdateDimension();
  const toast = useToast();
  const pending = createMutation.isPending || updateMutation.isPending;

  function submit() {
    const trimmedLabel = label.trim();
    if (!trimmedLabel) {
      setError('请填写维度名称。');
      return;
    }
    // Stricter than the backend here on purpose in edit mode too: keeps
    // `label` and the already-generated `key` from visually diverging,
    // even though DimensionUpdate itself has no "/" check (key can't
    // change on edit, so there is no routing risk to guard against there
    // — design doc §4.3, issue #13).
    if (trimmedLabel.includes('/')) {
      setError('名称不能包含斜杠(/)');
      return;
    }
    setError('');

    const trimmedDefaultValue = defaultValue.trim();
    // null, never undefined — see design doc §4.2 (issue #13) for why an
    // omitted default_value key means something different from an
    // explicit null to the backend.
    const submittedDefaultValue = trimmedDefaultValue === '' ? null : trimmedDefaultValue;
    const clampedWeight = Math.min(100, Math.max(1, parseInt(weight, 10) || 50));

    const mutation = isEdit
      ? updateMutation.mutateAsync({
          key: target.key,
          label: trimmedLabel,
          weight: clampedWeight,
          default_value: submittedDefaultValue,
        })
      : createMutation.mutateAsync({
          label: trimmedLabel,
          field_type: fieldType,
          weight: clampedWeight,
          default_value: submittedDefaultValue,
        });

    mutation
      .then(() => {
        toast.ok(
          isEdit ? `已更新维度「${trimmedLabel}」` : `已新增维度「${trimmedLabel}」，需要到「知识库设置」里为具体知识库启用后才能使用`,
        );
        onClose();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试');
      });
  }

  return (
    <Modal
      title={isEdit ? `编辑维度 · ${target.label}` : '新增维度'}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button type="button" className="btn primary" disabled={pending} onClick={submit}>
            确 定
          </button>
        </>
      }
    >
      <div className="mf">
        <label>
          <span className="req">*</span>维度名称
        </label>
        <input type="text" placeholder="例如：部门 / 标签 / 复核周期" value={label} maxLength={100} onChange={(e) => setLabel(e.target.value)} />
        <div className="hint">
          {isEdit
            ? `key「${target.key}」创建后不可修改；字段类型「${FIELD_TYPE_LABEL[target.field_type]}」创建后不可修改。`
            : '新增时会同时作为内部标识(key)；创建后 key 不可更改，显示名称之后仍可修改。'}
        </div>
      </div>
      <div className="mf">
        <label>
          <span className="req">*</span>字段类型
        </label>
        <select value={fieldType} disabled={isEdit} onChange={(e) => setFieldType(e.target.value as Dimension['field_type'])}>
          <option value="text">文本</option>
          <option value="number">数值</option>
          <option value="date">时间</option>
          <option value="boolean">布尔</option>
        </select>
        <div className="hint">创建后不可修改，用于答案条件的取值输入校验。</div>
      </div>
      <div className="mf">
        <label>
          <span className="req">*</span>权重(1–100)
        </label>
        <input type="number" min={1} max={100} value={weight} onChange={(e) => setWeight(e.target.value)} />
        <div className="hint">两条答案条件同样具体、又都没有精确命中查询时，涉及维度的权重总和更高的答案优先返回。</div>
      </div>
      <div className="mf">
        <label>默认取值提示(可选)</label>
        <ValueInput
          dim={{ key: '', label: '', weight: 0, field_type: fieldType }}
          value={defaultValue}
          onChange={setDefaultValue}
          allowUnset
        />
        <div className="hint">仅作为「写答案」时该维度输入框的预填提示，不做强制校验。</div>
      </div>
      {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
    </Modal>
  );
}

function ToggleDimensionStatusModal({ target, onClose }: { target: AdminDimension; onClose: () => void }) {
  const willDeactivate = target.status === 'active';
  const mutation = useSetDimensionStatus();
  const toast = useToast();

  function confirm() {
    mutation
      .mutateAsync({ key: target.key, status: willDeactivate ? 'deprecated' : 'active' })
      .then(() => {
        toast.ok('已更新维度状态');
        onClose();
      })
      .catch((err: unknown) => {
        toast.err(err instanceof ApiError ? err.message : '操作失败，请稍后重试');
        onClose();
      });
  }

  return (
    <Modal
      title={willDeactivate ? '停用维度' : '启用维度'}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button
            type="button"
            className={willDeactivate ? 'btn danger' : 'btn primary'}
            disabled={mutation.isPending}
            onClick={confirm}
          >
            确 定
          </button>
        </>
      }
    >
      <p style={{ fontSize: '13.5px', color: 'var(--ink-2)', lineHeight: 1.8 }}>
        即将{willDeactivate ? '停用' : '启用'}维度 <b style={{ color: 'var(--ink-1)' }}>{target.label}</b>。
      </p>
      {willDeactivate && (
        <div className="risk">
          已有 {target.answer_count} 条答案写入过该维度的取值，停用不会影响这些历史数据，仅新增/编辑答案时不再出现该字段。
        </div>
      )}
    </Modal>
  );
}
