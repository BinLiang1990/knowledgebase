import { useState } from 'react';
import { ApiError } from '../api/client';
import { useUpdateKnowledgePointTitle } from '../api/knowledgePoints';
import { Modal } from './ui/Modal';
import { useToast } from './ui/Toast';

interface EditTitleModalProps {
  kbId: number;
  kpId: number;
  currentTitle: string;
  onClose: () => void;
}

export function EditTitleModal({ kbId, kpId, currentTitle, onClose }: EditTitleModalProps) {
  const [title, setTitle] = useState(currentTitle);
  const [error, setError] = useState('');
  const updateMutation = useUpdateKnowledgePointTitle(kbId, kpId);
  const toast = useToast();

  function submit() {
    const trimmed = title.trim();
    if (!trimmed) {
      setError('请填写标题。');
      return;
    }
    setError('');
    updateMutation
      .mutateAsync(trimmed)
      .then(() => {
        toast.ok('已更新标题');
        onClose();
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试'));
  }

  return (
    <Modal
      title="编辑标题"
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button type="button" className="btn primary" disabled={updateMutation.isPending} onClick={submit}>
            确 定
          </button>
        </>
      }
    >
      <div className="mf">
        <label>
          <span className="req">*</span>标题
        </label>
        <input type="text" maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
    </Modal>
  );
}
