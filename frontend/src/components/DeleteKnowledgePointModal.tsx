import { useState } from 'react';
import { ApiError } from '../api/client';
import { useDeleteKnowledgePoint } from '../api/knowledgePoints';
import { Modal } from './ui/Modal';
import { useToast } from './ui/Toast';

// Shared by KnowledgePointListPage (issue #7) and KnowledgePointDetailPage
// (issue #8) — extracted rather than duplicated since both pages need the
// exact same delete-reason validation and error handling.
export function DeleteKnowledgePointModal({
  kbId,
  target,
  onClose,
}: {
  kbId: number;
  target: { id: number; title: string };
  onClose: () => void;
}) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const deleteMutation = useDeleteKnowledgePoint(kbId);
  const toast = useToast();

  function submit() {
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setError('请填写删除原因。');
      return;
    }
    setError('');
    deleteMutation
      .mutateAsync({ id: target.id, deleteReason: trimmedReason })
      .then(() => {
        // Doesn't promise recycle-bin recovery — this app has no recycle-
        // bin page yet (design doc §4.5 omits it for the same reason).
        // The backend does support restoring a soft-deleted knowledge
        // point, but not through any UI a user can reach today. Kimi 终审
        // finding on PR #24.
        toast.ok(`已删除「${target.title}」`);
        onClose();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试');
      });
  }

  return (
    <Modal
      title="删除知识点"
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button type="button" className="btn danger" disabled={deleteMutation.isPending} onClick={submit}>
            确 定 删 除
          </button>
        </>
      }
    >
      <p style={{ fontSize: '13.5px', color: 'var(--ink-2)', marginBottom: 12 }}>
        即将删除知识点 <b style={{ color: 'var(--ink-1)' }}>{target.title}</b>，及其全部答案。
      </p>
      <div className="mf">
        <label>
          <span className="req">*</span>删除原因
        </label>
        <textarea
          rows={2}
          placeholder="请说明删除原因，将记录在留痕中"
          value={reason}
          maxLength={500}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
      <div className="risk">
        采用软删除：删除后不再出现在知识点列表与查询结果中；数据与全部历史答案会保留，如需恢复请联系管理员。
      </div>
      {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
    </Modal>
  );
}
