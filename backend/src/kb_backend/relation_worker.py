"""答案关联后台 worker（docs/PRD-答案关联.md §0.8）。

MySQL 任务表即队列：单个进程内 daemon 线程轮询 relation_task，乐观 UPDATE
认领 pending 任务逐个执行。启动时把遗留的 generating（上次进程死在任务
中途）重置回 pending（PRD §8.2）。网关未配置时 worker 根本不会启动
（见 main.py 的 lifespan），已登记的任务保留在表里等配置好后处理。
"""
from __future__ import annotations

import logging
import threading

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_session_factory
from .models.relation import RelationTask
from .relations import RETRY_LIMIT, execute_analyze_task, execute_generate_pair_task

logger = logging.getLogger("kb_backend")

_POLL_SECONDS = 1.0
_FAILURE_PAUSE_SECONDS = 2.0


class RelationWorker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="relation-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._thread.join(timeout=timeout)

    # ---- internals ----

    def _run(self) -> None:
        session_factory = get_session_factory()
        try:
            with session_factory() as db:
                self._recover_orphans(db)
        except Exception:
            # 数据库暂不可用不应让线程死掉——轮询循环里会再遇到并继续重试
            logger.exception("relation worker: 启动恢复失败")

        logger.info("relation worker: started")
        while not self._stop.is_set():
            try:
                with session_factory() as db:
                    task = self._claim(db)
                    if task is None:
                        self._stop.wait(_POLL_SECONDS)
                        continue
                    self._execute(db, task)
            except Exception:
                logger.exception("relation worker: 轮询循环异常")
                self._stop.wait(_FAILURE_PAUSE_SECONDS)
        logger.info("relation worker: stopped")

    @staticmethod
    def _recover_orphans(db: Session) -> None:
        result = db.execute(
            update(RelationTask).where(RelationTask.status == "generating").values(status="pending")
        )
        db.commit()
        if result.rowcount:
            logger.info("relation worker: %s 个遗留 generating 任务重置为 pending", result.rowcount)

    @staticmethod
    def _claim(db: Session) -> RelationTask | None:
        task = db.execute(
            select(RelationTask)
            .where(RelationTask.status == "pending")
            .order_by(RelationTask.updated_at)
            .limit(1)
        ).scalar_one_or_none()
        if task is None:
            return None
        # 乐观认领：条件里带 status='pending'，被并发认领时 rowcount=0。
        # 当前只有单 worker，这是为将来多实例部署留的正确性保证。
        result = db.execute(
            update(RelationTask)
            .where(RelationTask.id == task.id, RelationTask.status == "pending")
            .values(status="generating", last_error=None)
        )
        db.commit()
        if result.rowcount != 1:
            return None
        db.refresh(task)
        return task

    def _execute(self, db: Session, task: RelationTask) -> None:
        settings = get_settings()
        logger.info("relation worker: 执行任务 #%s kind=%s kp=%s", task.id, task.kind, task.knowledge_point_id)
        try:
            if task.kind == "analyze":
                execute_analyze_task(db, task, settings)
            else:
                execute_generate_pair_task(db, task, settings)
            task.status = "done"
            task.last_error = None
            db.commit()
            logger.info("relation worker: 任务 #%s 完成", task.id)
        except Exception as exc:  # GatewayError、DB 异常等统一走重试
            db.rollback()
            task = db.get(RelationTask, task.id)
            if task is None:
                return
            task.retry_count += 1
            task.last_error = str(exc)[:500]
            task.status = "failed" if task.retry_count >= RETRY_LIMIT else "pending"
            db.commit()
            logger.warning(
                "relation worker: 任务 #%s 失败(第 %s 次)：%s", task.id, task.retry_count, exc
            )
            self._stop.wait(_FAILURE_PAUSE_SECONDS)


def start_relation_worker() -> RelationWorker | None:
    """网关配置齐全才启动；返回 None 表示功能处于 disabled 降级态。"""
    if not get_settings().relation_analysis_enabled:
        logger.info("relation worker: 未配置模型网关，答案关联分析处于禁用状态")
        return None
    worker = RelationWorker()
    worker.start()
    return worker
