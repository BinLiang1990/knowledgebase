import { useState } from 'react';
import type { Dimension } from '../api/dimensions';
import { ApiError } from '../api/client';
import { diffCoord, useCreateAnswer, useEditAnswer } from '../api/answers';
import type { Filters } from './ui/dimensionValue';
import { CoordEditor, coordRowsFromCoord, coordRowsToCoord, hasLockedRow } from './CoordEditor';
import type { CoordRow } from './CoordEditor';
import { Modal } from './ui/Modal';
import { useToast } from './ui/Toast';
import { today } from '../lib/today';

export interface ExistingAnswer {
  answerId: number;
  coord: Filters;
  content: string;
  effective_time: string;
  note: string | null;
}

interface WriteAnswerModalProps {
  kbId: number;
  kpId: number;
  dimensions: Dimension[];
  existing?: ExistingAnswer;
  onClose: () => void;
}

// Shared by "+ 写一条答案" (existing undefined) and a group row's "编辑"
// (existing set) — mirrors the demo's single shared #ansMask modal. Design
// doc §4.2-§4.4.
export function WriteAnswerModal({ kbId, kpId, dimensions, existing, onClose }: WriteAnswerModalProps) {
  const isEdit = existing !== undefined;
  const [content, setContent] = useState(existing?.content ?? '');
  // Kimi 终审 finding on PR #24: this used to always start at today(),
  // silently moving an existing answer's effective date forward the moment
  // its content/conditions were edited for any other reason.
  const [effectiveTime, setEffectiveTime] = useState(existing?.effective_time ?? today());
  const [note, setNote] = useState(existing?.note ?? '');
  const [rows, setRows] = useState<CoordRow[]>(() =>
    existing ? coordRowsFromCoord(existing.coord, dimensions) : [],
  );
  const [migrationReason, setMigrationReason] = useState('');
  const [error, setError] = useState('');
  const createMutation = useCreateAnswer(kbId, kpId);
  const editMutation = useEditAnswer(kbId, kpId);
  const toast = useToast();

  function submit() {
    const trimmedContent = content.trim();
    if (!trimmedContent || !effectiveTime) {
      setError('答案内容、生效时间为必填项。');
      return;
    }
    const result = coordRowsToCoord(rows, dimensions);
    if (result.error || !result.coord) {
      setError(result.error ?? '条件填写有误。');
      return;
    }
    const coord = result.coord;
    const trimmedNote = note.trim() || undefined;

    if (!isEdit) {
      createMutation
        .mutateAsync({ coord, content: trimmedContent, effective_time: effectiveTime, note: trimmedNote })
        .then(() => {
          toast.ok('已保存答案');
          onClose();
        })
        .catch((err: unknown) => setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试'));
      return;
    }

    const changed = diffCoord(existing.coord, coord, dimensions);
    if (changed && hasLockedRow(rows)) {
      // §4.2/§4.4: the coord always includes the locked row's original
      // value verbatim, which normalize_coord would reject server-side
      // (the dimension it references is no longer enabled) — block here
      // with a message the user can actually act on, instead of a 400.
      setError('该答案的条件包含已停用的维度，暂不支持迁移条件；如需修改，请只调整内容或生效时间。');
      return;
    }
    if (changed && !migrationReason.trim()) {
      setError('变更适用条件需要填写迁移原因。');
      return;
    }

    editMutation
      .mutateAsync({
        answerId: existing.answerId,
        content: trimmedContent,
        effective_time: effectiveTime,
        note: trimmedNote,
        // Omit `coord` entirely when unchanged — see design doc §4.4 for
        // why "always send it" would break editing an answer whose coord
        // references a since-disabled dimension.
        ...(changed ? { coord, migration_reason: migrationReason.trim() } : {}),
      })
      .then(() => {
        toast.ok('已保存答案');
        onClose();
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试'));
  }

  const isPending = createMutation.isPending || editMutation.isPending;
  const currentCoordResult = coordRowsToCoord(rows, dimensions);
  const showMigrationReason =
    isEdit && !!currentCoordResult.coord && diffCoord(existing.coord, currentCoordResult.coord, dimensions);

  return (
    <Modal
      title={isEdit ? '编辑答案' : '写一条答案'}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button type="button" className="btn primary" disabled={isPending} onClick={submit}>
            确 定
          </button>
        </>
      }
    >
      <div className="mf">
        <label>
          <span className="req">*</span>答案内容
        </label>
        <textarea
          rows={3}
          placeholder="这个条件组合下的说法"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
      </div>
      <div className="mf">
        <label>
          <span className="req">*</span>生效时间
        </label>
        <input type="date" value={effectiveTime} onChange={(e) => setEffectiveTime(e.target.value)} />
      </div>
      <div className="mf">
        <label>适用条件(只写你关心的；全部移除 = 默认答案，处处适用)</label>
        <CoordEditor dimensions={dimensions} rows={rows} onChange={setRows} />
      </div>
      {showMigrationReason && (
        <div className="mf">
          <label>
            <span className="req">*</span>迁移原因
          </label>
          <input
            type="text"
            placeholder="条件变化后为什么要迁移，将记录在留痕中"
            value={migrationReason}
            onChange={(e) => setMigrationReason(e.target.value)}
          />
        </div>
      )}
      <div className="mf">
        <label>变更说明(可选)</label>
        <input type="text" placeholder="例如：流程调整" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
    </Modal>
  );
}
