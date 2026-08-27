"""Langfuse 全链路可观测集成。

设计约束：
- 未配置 LANGFUSE_PUBLIC_KEY / SECRET_KEY / HOST 时全部函数为 no-op，离线运行不受影响；
- Langfuse 客户端的一切异常都在本模块内吞掉，绝不影响研究工作流本身；
- 通过线程本地变量维护"当前 run 的 trace"，LLM generation 自动挂到所属 trace 下
  （inline 与 Celery solo 池下工作流均在单线程内同步执行）。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger("verda.observability")

_local = threading.local()
_client_lock = threading.Lock()


def get_langfuse():
    """惰性单例；未配置或初始化失败返回 None。"""
    client = getattr(_local, "client", "unset")
    if client is not None and client != "unset":
        return client
    with _client_lock:
        if getattr(_local, "client", "unset") != "unset":
            return _local.client
        settings = get_settings()
        if not (settings.langfuse_public_key and settings.langfuse_secret_key and settings.langfuse_host):
            _local.client = None
            return None
        try:
            from langfuse import Langfuse

            _local.client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host.rstrip("/"),
            )
        except Exception:
            logger.warning("langfuse init failed; observability disabled", exc_info=True)
            _local.client = None
    return _local.client


def reset_for_tests() -> None:
    """测试隔离：清空线程本地状态，让下一次调用重新读取配置。"""
    _local.client = "unset"
    _local.trace = None


def start_run_trace(*, run_id: int, task_id: int, prompt: str, scope: dict[str, Any] | None) -> None:
    """run 开始时建立 trace（幂等：已有 trace 则跳过）。"""
    client = get_langfuse()
    if client is None:
        return
    try:
        if getattr(_local, "trace", None) is not None:
            return
        _local.trace = client.trace(
            name="research_run",
            id=f"run-{run_id}",
            input={"task_id": task_id, "run_id": run_id, "prompt": prompt},
            metadata={"task_id": task_id, "run_id": run_id, "scope": scope or {}},
            tags=["competitive_research"],
        )
    except Exception:
        logger.warning("langfuse start_run_trace failed", exc_info=True)
        _local.trace = None


def end_run_trace(*, status: str, output: dict[str, Any] | None = None) -> None:
    """run 结束时回写最终状态并尝试冲刷缓冲。"""
    trace = getattr(_local, "trace", None)
    client = get_langfuse()
    _local.trace = None
    if trace is None or client is None:
        return
    try:
        trace.update(output={"status": status, **(output or {})})
        client.flush()
    except Exception:
        logger.warning("langfuse end_run_trace failed", exc_info=True)


def record_node_span(
    *,
    node_name: str,
    status: str,
    started_at: datetime | None = None,
    duration_ms: int = 0,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """记录单个工作流节点的 span（成功/失败都记），失败节点 level=ERROR。"""
    client = get_langfuse()
    if client is None:
        return
    trace = getattr(_local, "trace", None)
    if trace is None:
        return
    try:
        end_at = datetime.now(timezone.utc)
        start = started_at or end_at
        trace.span(
            name=node_name,
            input=input_summary,
            output=output_summary,
            start_time=start,
            end_time=start + timedelta(milliseconds=max(duration_ms, 0)),
            level="ERROR" if status == "failed" else "DEFAULT",
            status_message=error,
            metadata={"node_status": status, "duration_ms": duration_ms},
        )
    except Exception:
        logger.warning("langfuse record_node_span failed", exc_info=True)


def record_generation(
    *,
    name: str,
    model: str,
    input_messages: list[dict[str, Any]] | None = None,
    output_content: Any = None,
    usage: dict[str, Any] | None = None,
    started_at: datetime | None = None,
    duration_ms: int = 0,
    error: str | None = None,
    metadata_extra: dict[str, Any] | None = None,
) -> None:
    """记录一次 LLM 调用（generation），自动挂到当前 run 的 trace 下。"""
    client = get_langfuse()
    if client is None:
        return
    try:
        end_at = datetime.now(timezone.utc)
        start = started_at or end_at
        usage_payload = {
            "promptTokens": usage.get("prompt_tokens", 0) or 0,
            "completionTokens": usage.get("completion_tokens", 0) or 0,
            "totalTokens": usage.get("total_tokens", 0) or 0,
        } if usage else None
        metadata = {"duration_ms": duration_ms, **(metadata_extra or {})}
        trace = getattr(_local, "trace", None)
        if trace is not None:
            trace.generation(
                name=name,
                model=model,
                input=input_messages,
                output=output_content,
                usage=usage_payload,
                start_time=start,
                end_time=start + timedelta(milliseconds=max(duration_ms, 0)),
                level="ERROR" if error else "DEFAULT",
                status_message=error,
                metadata=metadata,
            )
        else:
            # 工作流上下文之外（如将来单独调用 LLM），退化为独立 trace。
            client.trace(name=name).generation(
                name=name,
                model=model,
                input=input_messages,
                output=output_content,
                usage=usage_payload,
                start_time=start,
                end_time=start + timedelta(milliseconds=max(duration_ms, 0)),
                level="ERROR" if error else "DEFAULT",
                status_message=error,
            )
    except Exception:
        logger.warning("langfuse record_generation failed", exc_info=True)


def flush() -> None:
    """手动冲刷缓冲（进程退出前调用，保证 trace 落库）。"""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.warning("langfuse flush failed", exc_info=True)
