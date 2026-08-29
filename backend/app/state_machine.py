"""任务/Run 状态机：集中式迁移表与转换函数。

依据《深度研究Agent主链路改造方案》§6：所有状态转换集中在同一模块，
API、Celery 与 inline 模式复用同一套转换函数；非法转换抛出明确错误，
由 API 层（app/api/deps.py::task_error）映射为 HTTP 409。

迁移表包含两类边：
- 方案 §6.3 定义的目标迁移边；
- 保留现状的兜底边（标记 legacy），例如入队失败兜底 queued→failed、
  手动重生成报告复用最新 Run 的 completed→running 等，均已回写方案文档。
"""

from app import models

# Task 状态迁移表（§6.3 + 兜底边，标 legacy 的为保留现状的兜底路径）
TASK_TRANSITIONS: dict[str, set[str]] = {
    models.TaskStatus.draft.value: {
        models.TaskStatus.clarifying.value,
        models.TaskStatus.confirmed.value,
        models.TaskStatus.canceled.value,
    },
    models.TaskStatus.clarifying.value: {
        models.TaskStatus.waiting_input.value,
        models.TaskStatus.confirmed.value,
        models.TaskStatus.canceled.value,
    },
    models.TaskStatus.waiting_input.value: {
        models.TaskStatus.clarifying.value,
        models.TaskStatus.confirmed.value,
        models.TaskStatus.canceled.value,
    },
    models.TaskStatus.confirmed.value: {
        models.TaskStatus.queued.value,
        models.TaskStatus.canceled.value,
    },
    # legacy: queued→failed 为确认后入队失败的兜底路径（mark_run_failed）
    models.TaskStatus.queued.value: {
        models.TaskStatus.running.value,
        models.TaskStatus.failed.value,
        models.TaskStatus.canceled.value,
    },
    models.TaskStatus.running.value: {
        models.TaskStatus.waiting_review.value,
        models.TaskStatus.completed.value,
        models.TaskStatus.completed_with_limitations.value,
        models.TaskStatus.failed.value,
        models.TaskStatus.canceled.value,
    },
    # legacy: waiting_review→queued/failed 为重跑与审核失败兜底路径
    models.TaskStatus.waiting_review.value: {
        models.TaskStatus.queued.value,
        models.TaskStatus.running.value,
        models.TaskStatus.completed.value,
        models.TaskStatus.completed_with_limitations.value,
        models.TaskStatus.failed.value,
        models.TaskStatus.canceled.value,
    },
    models.TaskStatus.failed.value: {models.TaskStatus.queued.value},
    # legacy: completed→queued / canceled→queued 为 rerun 与手动重生成路径
    models.TaskStatus.completed.value: {models.TaskStatus.queued.value},
    models.TaskStatus.completed_with_limitations.value: {models.TaskStatus.queued.value},
    models.TaskStatus.canceled.value: {models.TaskStatus.queued.value},
}

# Run 状态迁移表（Run 侧此前无校验，本表为首次集中化；
# 标 legacy 的为保留现状代码实际依赖的兜底边）
RUN_TRANSITIONS: dict[str, set[str]] = {
    # legacy: queued→failed 为入队失败兜底路径（mark_run_failed）
    models.RunStatus.queued.value: {
        models.RunStatus.running.value,
        models.RunStatus.failed.value,
        models.RunStatus.canceled.value,
    },
    models.RunStatus.running.value: {
        models.RunStatus.waiting_review.value,
        models.RunStatus.completed.value,
        models.RunStatus.completed_with_limitations.value,
        models.RunStatus.failed.value,
        models.RunStatus.canceled.value,
    },
    # legacy: waiting_review→queued/failed 为重跑与审核失败兜底路径
    models.RunStatus.waiting_review.value: {
        models.RunStatus.queued.value,
        models.RunStatus.running.value,
        models.RunStatus.completed.value,
        models.RunStatus.completed_with_limitations.value,
        models.RunStatus.failed.value,
        models.RunStatus.canceled.value,
    },
    # legacy: failed→canceled 为用户取消失败任务的路径；
    # failed→running 为 resume 直接从失败点恢复执行的路径（prepare_run_for_resume）
    models.RunStatus.failed.value: {
        models.RunStatus.queued.value,
        models.RunStatus.running.value,
        models.RunStatus.canceled.value,
    },
    # legacy: completed→running 为手动重生成报告复用最新 Run 的路径
    models.RunStatus.completed.value: {models.RunStatus.running.value},
    models.RunStatus.completed_with_limitations.value: {models.RunStatus.queued.value},
    models.RunStatus.canceled.value: set(),
}

ACTIVE_RUN_STATUSES = {models.RunStatus.queued.value, models.RunStatus.running.value}


def transition_task(
    task: models.ResearchTask,
    target_status: models.TaskStatus,
    *,
    reason: str | None = None,
) -> None:
    """校验并执行 Task 状态转换；非法转换抛 ValueError（API 层映射 409）。"""
    current_status = task.status
    next_status = target_status.value
    if current_status == next_status:
        return
    if next_status not in TASK_TRANSITIONS.get(current_status, set()):
        raise ValueError(f"invalid_task_transition:{current_status}:{next_status}")

    now = models.utc_now()
    task.status = next_status
    if target_status == models.TaskStatus.confirmed:
        task.confirmed_at = now
    if target_status == models.TaskStatus.queued:
        task.queued_at = now
        task.completed_at = None
        task.failure_reason = None
    if target_status in {models.TaskStatus.completed, models.TaskStatus.completed_with_limitations}:
        task.completed_at = now
    if target_status == models.TaskStatus.failed:
        task.failure_reason = reason


def transition_run(run: models.TaskRun, target_status: models.RunStatus) -> None:
    """校验并执行 Run 状态转换；非法转换抛 ValueError（API 层映射 409）。

    与 transition_task 不同，Run 的时间戳/阶段字段由调用方按语义自行维护
    （started_at/finished_at/current_stage 在各写入点含义不同），本函数只
    负责校验与写入 status。
    """
    current_status = run.status
    next_status = target_status.value
    if current_status == next_status:
        return
    if next_status not in RUN_TRANSITIONS.get(current_status, set()):
        raise ValueError(f"invalid_run_transition:{current_status}:{next_status}")
    run.status = next_status
