import { useState } from 'react';
import { ApiError } from '../api/client';
import { useRevokeAnswer } from '../api/answers';
import { Modal } from './ui/Modal';
import { useToast } from './ui/Toast';

// Shared by KnowledgePointDetailPage's "变更留痕" tab and OperationLogPage
// (issue #14) — both trigger a revoke from an existing answer_id, per
// issue #10's own convention (answer_id, not a client-reconstructed
// coord). kbId/kpId are resolved by the CALLER (ChangeLogTable — see
// design doc §4.4): the knowledge-point-scoped page passes its own route
// params for every row, but the global log page's rows each carry their
// own knowledge_base_id/knowledge_point_id, so the same row-level answerId
// can belong to a different knowledge base each time. useRevokeAnswer is
// only instantiated HERE, inside the modal, once kbId/kpId are known for
// this specific answer — not by the caller ahead of time.
export function RevokeAnswerModal({
  kbId,
  kpId,
  answerId,
  content,
  onClose,
}: {
  kbId: number;
  kpId: number;
  answerId: number;
  content: string;
  onClose: () => void;
}) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const revokeMutation = useRevokeAnswer(kbId, kpId);
  const toast = useToast();

  function submit() {
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setError('请填写撤回原因。');
      return;
    }
    setError('');
    revokeMutation
      .mutateAsync({ answerId, revokeReason: trimmedReason })
      .then(() => {
        toast.ok('已撤回该条件下的答案');
        onClose();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试');
      });
  }

  return (
    <Modal
      title="撤回答案"
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button type="button" className="btn danger" disabled={revokeMutation.isPending} onClick={submit}>
            确 认 撤 回
          </button>
        </>
      }
    >
      <p style={{ fontSize: '13.5px', color: 'var(--ink-2)', lineHeight: 1.9, marginBottom: 12 }}>
        将撤回这个条件下的答案：
        <br />
        <b style={{ color: 'var(--ink-1)' }}>{content}</b>
      </p>
      <div className="mf">
        <label>
          <span className="req">*</span>撤回原因
        </label>
        <input
          type="text"
          placeholder="必填，写入留痕"
          value={reason}
          maxLength={500}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
      <div className="risk">撤回为逻辑删除：该条件下将不再返回此答案；历史版本与留痕永久保留。</div>
      {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
    </Modal>
  );
}
