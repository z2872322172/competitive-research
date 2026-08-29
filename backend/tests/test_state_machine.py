"""集中状态机测试：Task/Run 迁移表全遍历 + 转换副作用 + 错误码契约（方案 §6.3）。"""

import pytest

from app import models
from app.state_machine import (
    RUN_TRANSITIONS,
    TASK_TRANSITIONS,
    transition_run,
    transition_task,
)


def _make_task(status: str) -> models.ResearchTask:
    return models.ResearchTask(title="t", prompt="p", status=status)


def _make_run(status: str) -> models.TaskRun:
    return models.TaskRun(task_id=1, status=status)


def test_task_transition_table_covers_all_statuses():
    all_statuses = {status.value for status in models.TaskStatus}
    assert set(TASK_TRANSITIONS.keys()) == all_statuses


def test_run_transition_table_covers_all_statuses():
    all_statuses = {status.value for status in models.RunStatus}
    assert set(RUN_TRANSITIONS.keys()) == all_statuses


def test_task_legal_transitions_all_succeed():
    for current_value, allowed in TASK_TRANSITIONS.items():
        for next_value in allowed:
            task = _make_task(current_value)
            transition_task(task, models.TaskStatus(next_value))
            assert task.status == next_value


def test_task_illegal_transitions_all_raise():
    all_statuses = {status.value for status in models.TaskStatus}
    for current_value, allowed in TASK_TRANSITIONS.items():
        for next_value in all_statuses - allowed - {current_value}:
            task = _make_task(current_value)
            with pytest.raises(ValueError) as exc_info:
                transition_task(task, models.TaskStatus(next_value))
            assert str(exc_info.value) == f"invalid_task_transition:{current_value}:{next_value}"


def test_run_legal_transitions_all_succeed():
    for current_value, allowed in RUN_TRANSITIONS.items():
        for next_value in allowed:
            run = _make_run(current_value)
            transition_run(run, models.RunStatus(next_value))
            assert run.status == next_value


def test_run_illegal_transitions_all_raise():
    all_statuses = {status.value for status in models.RunStatus}
    for current_value, allowed in RUN_TRANSITIONS.items():
        for next_value in all_statuses - allowed - {current_value}:
            run = _make_run(current_value)
            with pytest.raises(ValueError) as exc_info:
                transition_run(run, models.RunStatus(next_value))
            assert str(exc_info.value) == f"invalid_run_transition:{current_value}:{next_value}"


def test_same_status_transition_is_noop():
    task = _make_task(models.TaskStatus.running.value)
    transition_task(task, models.TaskStatus.running)
    assert task.status == models.TaskStatus.running.value

    run = _make_run(models.RunStatus.running.value)
    transition_run(run, models.RunStatus.running)
    assert run.status == models.RunStatus.running.value


def test_clarifying_states_only_belong_to_task():
    # clarifying/waiting_input 仅属于 Task，不属于 Run（方案 §6.3 迁移规则）
    for status in (models.TaskStatus.clarifying, models.TaskStatus.waiting_input):
        assert status.value in TASK_TRANSITIONS
        assert status.value not in RUN_TRANSITIONS


def test_transition_task_records_side_effects():
    task = _make_task(models.TaskStatus.draft.value)
    transition_task(task, models.TaskStatus.confirmed)
    assert task.confirmed_at is not None

    task.completed_at = models.utc_now()
    task.failure_reason = "boom"
    transition_task(task, models.TaskStatus.queued)
    assert task.queued_at is not None
    assert task.completed_at is None
    assert task.failure_reason is None

    transition_task(task, models.TaskStatus.failed, reason="step crashed")
    assert task.failure_reason == "step crashed"


def test_transition_task_completed_with_limitations_sets_completed_at():
    task = _make_task(models.TaskStatus.running.value)
    transition_task(task, models.TaskStatus.completed_with_limitations)
    assert task.completed_at is not None
    assert task.status == models.TaskStatus.completed_with_limitations.value


def test_transition_run_unknown_status_raises():
    run = _make_run(models.RunStatus.completed.value)
    with pytest.raises(ValueError) as exc_info:
        transition_run(run, models.RunStatus.waiting_review)
    assert str(exc_info.value) == "invalid_run_transition:completed:waiting_review"
