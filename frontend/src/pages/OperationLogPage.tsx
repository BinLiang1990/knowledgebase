import { useGlobalChangeLog } from '../api/changeLog';
import { AppShell } from '../components/layout/AppShell';
import { ChangeLogTable } from '../components/ChangeLogTable';

export function OperationLogPage() {
  const query = useGlobalChangeLog();

  return (
    <AppShell title="操作日志" crumb="全局 / 操作日志">
      <div className="notice">
        跨全部知识库的答案变更流水：写答案 / 改答案 / 撤回答案，每一步都留痕，不可物理删除。「操作」列可以直接对仍然生效的答案执行撤回。
      </div>

      <div className="card ov">
        <div className="card-head">
          <span className="tick" />
          <h3>全量变更留痕</h3>
          <span className="sub">每个知识库、每个知识点、每次撤回，都可在此追溯</span>
        </div>

        {query.isLoading && (
          <div className="empty-block">
            <span className="spin" /> 加载中…
          </div>
        )}
        {query.isError && (
          <div className="empty-block">
            加载失败，请检查网络或后端服务后
            <br />
            <a onClick={() => query.refetch()}>重试</a>
          </div>
        )}
        {!query.isLoading && !query.isError && <ChangeLogTable entries={query.data ?? []} showLocation />}
      </div>
    </AppShell>
  );
}
