import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useKnowledgeBases } from '../api/knowledgeBases';
import { useAdminDimensions, useEnabledDimensions, useSetEnabledDimensions, type Dimension } from '../api/dimensions';
import { ApiError } from '../api/client';
import { AppShell } from '../components/layout/AppShell';
import { KbTabs } from '../components/layout/KbTabs';
import { useToast } from '../components/ui/Toast';

const FIELD_TYPE_LABEL: Record<Dimension['field_type'], string> = {
  text: '文本',
  number: '数值',
  date: '时间',
  boolean: '布尔',
};

export function KnowledgeBaseSettingsPage() {
  const { kbId: kbIdParam } = useParams<{ kbId: string }>();
  const kbId = Number(kbIdParam);

  const { data: knowledgeBases, isLoading: kbLoading, isError: kbIsError, refetch: kbRefetch } = useKnowledgeBases();
  const kb = knowledgeBases?.find((k) => k.id === kbId);
  const kbReady = kb?.status === 'active';

  const adminDimensionsQuery = useAdminDimensions();
  const enabledDimensionsQuery = useEnabledDimensions(kbId, kbReady);
  const saveMutation = useSetEnabledDimensions(kbId);

  const [checkedKeys, setCheckedKeys] = useState<Set<string> | null>(null);
  const [error, setError] = useState('');
  const toast = useToast();

  // Tracks whether a fetch cycle for the CURRENT kbId has actually started
  // — see the seeding effect below for why this can't just be
  // `!enabledDimensionsQuery.isFetching`.
  const hasFetchedOnceRef = useRef(false);

  // React Router does not unmount/remount this component just because the
  // :kbId route param changed to a different value (it's still the same
  // matched route) — component-local state like checkedKeys would
  // otherwise keep whatever the PREVIOUS knowledge base's checklist looked
  // like, and the seeding effect below (guarded by `checkedKeys === null`)
  // would never re-seed for the new kbId, letting the user view/submit one
  // knowledge base's enabled set while looking at (and saving to) a
  // different one. Not reachable via any link this app currently renders
  // (every path to a different kbId's settings page currently goes through
  // the knowledge-point list route first, which does unmount this
  // component) but cheap to guard against regardless of whether a future
  // navigation path makes it reachable. Codex outer-gate finding on PR #29
  // (third round).
  useEffect(() => {
    setCheckedKeys(null);
    setError('');
    hasFetchedOnceRef.current = false;
  }, [kbId]);

  // Record every isFetching transition so the seeding effect below can
  // tell "a fetch for the current kbId has genuinely completed" apart from
  // "this query happens to read !isFetching on the very render before its
  // own background refetch has even been dispatched" — empirically, on a
  // remount with an existing (stale) cache entry, TanStack Query's first
  // render(s) after mount report `isFetching: false` with the OLD cached
  // data still in `data`, and only flip to `isFetching: true` a render or
  // two later once the actual refetch is under way. Gating the seed on
  // `!isFetching` alone (an earlier attempt at this same fix) seeded from
  // that stale snapshot before the refetch ever started, and — because the
  // seeding effect only ever runs while checkedKeys is null — permanently
  // ignored the fresh result that arrived afterward.
  //
  // This relies on the query's staleTime staying at the default 0 (never
  // configured otherwise in this codebase's createQueryClient) — that's
  // what guarantees every mount actually triggers a background refetch,
  // so isFetching is guaranteed to become true at least once. If a future
  // change raised staleTime for this or a shared default, an
  // already-fresh cache entry could skip straight past `isFetching: true`
  // and hasFetchedOnceRef would never flip, leaving checkedKeys stuck at
  // null. Noted here (Kimi 终审 comment on PR #29) rather than building a
  // more defensive mechanism now for a change that hasn't happened.
  useEffect(() => {
    if (enabledDimensionsQuery.isFetching) {
      hasFetchedOnceRef.current = true;
    }
  }, [enabledDimensionsQuery.isFetching]);

  // Seed local checkbox state from the currently-enabled set exactly once
  // per kbId, once a fetch for that kbId has actually started and
  // completed — a later background refetch (e.g. right after this page's
  // own save invalidates the query) must not clobber whatever the user has
  // since clicked. Mirrors the "form state initialized from server data,
  // then locally owned" pattern other forms in this codebase get for free
  // by only mounting after their data is already loaded (they live inside
  // a Modal opened with an already-fetched target); this page has no such
  // modal to defer behind, so the seeding has to be explicit. Codex
  // outer-gate finding on PR #29 (fourth round, see hasFetchedOnceRef above
  // for why a simpler `!isFetching` check isn't sufficient on its own).
  useEffect(() => {
    if (
      checkedKeys === null &&
      enabledDimensionsQuery.data &&
      !enabledDimensionsQuery.isFetching &&
      hasFetchedOnceRef.current
    ) {
      setCheckedKeys(new Set(enabledDimensionsQuery.data.map((d) => d.key)));
    }
  }, [checkedKeys, enabledDimensionsQuery.data, enabledDimensionsQuery.isFetching]);

  // Computed here (not just once further down, right before it's rendered)
  // so `save()` below can filter against it too — a dimension can be
  // globally deactivated by someone else while this page is open, which
  // (thanks to useSetDimensionStatus's own cache invalidation) refetches
  // adminDimensionsQuery and drops that dimension out of this filtered
  // list, hiding its checkbox. `checkedKeys` is independent local state
  // that nothing automatically prunes, so without this filter, Save would
  // still submit that now-inactive key — the backend would then reject the
  // *entire* save ("已停用，无法启用"), and the user would have no
  // checkbox left to uncheck to fix it, since it's no longer rendered.
  // Codex outer-gate finding on PR #29 (sixth round).
  const activeDimensions = (adminDimensionsQuery.data ?? []).filter((d) => d.status === 'active');

  function toggle(key: string) {
    setCheckedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function save() {
    setError('');
    const activeKeys = new Set(activeDimensions.map((d) => d.key));
    const keysToSubmit = Array.from(checkedKeys ?? []).filter((key) => activeKeys.has(key));
    saveMutation
      .mutateAsync(keysToSubmit)
      .then(() => {
        toast.ok('已保存本知识库启用的维度');
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试');
      });
  }

  if (kbLoading) {
    return (
      <AppShell title="知识库设置" crumb="知识库列表 / 知识库设置">
        {/* Number.isFinite guard — a malformed :kbId (e.g. non-numeric,
            NaN) must not render tab links pointing at
            /knowledge-bases/NaN/... while still in a loading/error state.
            Kimi 终审 finding on PR #29. */}
        {Number.isFinite(kbId) && <KbTabs kbId={kbId} active="settings" />}
        <div className="card">
          <div className="empty-block">
            <span className="spin" /> 加载中…
          </div>
        </div>
      </AppShell>
    );
  }

  if (kbIsError) {
    return (
      <AppShell title="知识库设置" crumb="知识库列表 / 知识库设置">
        {Number.isFinite(kbId) && <KbTabs kbId={kbId} active="settings" />}
        <div className="card">
          <div className="empty-block">
            加载知识库失败，请稍后重试
            <br />
            <span style={{ display: 'inline-block', marginTop: 12 }}>
              <a onClick={() => kbRefetch()}>重试</a>
            </span>
          </div>
        </div>
      </AppShell>
    );
  }

  if (!kb || kb.status !== 'active') {
    return (
      <AppShell title="知识库设置" crumb="知识库列表 / 知识库设置">
        <div className="card">
          <div className="empty-block">
            没有指定有效的知识库（可能已被停用或不存在）
            <br />
            <span style={{ display: 'inline-block', marginTop: 12 }}>
              <Link className="btn primary" to="/knowledge-bases">
                ‹ 返回知识库列表
              </Link>
            </span>
          </div>
        </div>
      </AppShell>
    );
  }

  const dataIsError = adminDimensionsQuery.isError || enabledDimensionsQuery.isError;
  // checkedKeys === null only means "still loading" while the underlying
  // query might still succeed — once enabledDimensionsQuery has actually
  // failed, it will never populate .data, so checkedKeys would stay null
  // forever and this must stop being treated as a loading state; otherwise
  // the error block below (guarded by `!dataLoading`) can never render and
  // the page is stuck on a permanent spinner with no retry control. Codex
  // outer-gate finding on PR #29.
  const dataLoading =
    adminDimensionsQuery.isLoading || enabledDimensionsQuery.isLoading || (checkedKeys === null && !dataIsError);

  return (
    <AppShell title="知识库设置" crumb={`${kb.name} / 知识库设置`}>
      <KbTabs kbId={kbId} active="settings" />

      <div className="notice">
        维度定义是<b>全局共享</b>的，但每个知识库需要单独勾选「启用」才能在写答案时用到该维度作为适用条件；停用/取消勾选不影响本知识库历史答案里已经写入的取值，只影响之后能否继续选用。
      </div>

      <div className="card ov">
        <div className="card-head">
          <span className="tick" />
          <h3>启用维度</h3>
          <span className="sub">从全局维度库中，选择本知识库「{kb.name}」要用到的维度</span>
          <span className="spacer" />
          <span className="ops">
            <Link to="/dimensions">前往维度管理 »</Link>
          </span>
        </div>

        {dataLoading && (
          <div className="empty-block">
            <span className="spin" /> 加载中…
          </div>
        )}
        {dataIsError && !dataLoading && (
          <div className="empty-block">
            加载失败，请检查网络或后端服务后
            <a
              onClick={() => {
                adminDimensionsQuery.refetch();
                enabledDimensionsQuery.refetch();
              }}
            >
              {' '}
              重试
            </a>
          </div>
        )}
        {!dataLoading && !dataIsError && activeDimensions.length === 0 && (
          <div className="empty-block">
            还没有任何启用中的全局维度，先去<Link to="/dimensions">「维度管理」</Link>新增一个。
          </div>
        )}
        {!dataLoading && !dataIsError && activeDimensions.length > 0 && (
          <div>
            {activeDimensions.map((dim) => (
              <label key={dim.key} className="chk" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <input type="checkbox" checked={checkedKeys?.has(dim.key) ?? false} onChange={() => toggle(dim.key)} />
                  <span style={{ fontWeight: 600, color: 'var(--ink-1)' }}>{dim.label}</span>
                  <span className="tag blue ftype-tag">{FIELD_TYPE_LABEL[dim.field_type]}</span>
                  <span className="field-hint">权重 {dim.weight}</span>
                </span>
                <span className="field-hint">全局共 {dim.answer_count} 条答案在用</span>
              </label>
            ))}
          </div>
        )}

        <div className="form-row" style={{ marginTop: 6 }}>
          {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
          {/* dataIsError must also disable this — dataLoading alone is false
              once a failed fetch settles (Codex outer-gate fix on PR #29's
              first round), and checkedKeys would still be null: clicking
              Save in that state would submit an empty dimension_keys list
              and silently wipe every dimension this knowledge base had
              enabled. Codex outer-gate finding on PR #29 (second round). */}
          <button
            type="button"
            className="btn primary"
            disabled={dataLoading || dataIsError || saveMutation.isPending}
            onClick={save}
          >
            保 存
          </button>
        </div>
      </div>
    </AppShell>
  );
}
