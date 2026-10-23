"""供模型调用和工具处理共用的请求停止控制。"""

from collections.abc import Callable
from enum import StrEnum
from threading import Event


class RequestStopReason(StrEnum):
    REQUEST_CANCELLED = "request_cancelled"
    REQUEST_DEADLINE_EXCEEDED = "request_deadline_exceeded"


class RequestStoppedError(RuntimeError):
    """本轮请求在检查点停止，与是否包含工具调用无关。"""

    def __init__(self, reason: RequestStopReason):
        self.reason = reason
        super().__init__(f"Request stopped due to: {reason.value}")


def check_request_cancelled(cancel_event: Event | None) -> None:
    """信号已设置时抛出请求停止异常；缺少信号或未取消时正常返回。

    此函数只检查信号，不会强行终止正在运行的模型调用或工具。
    """
    if cancel_event is None:
        return
    if not cancel_event.is_set():
        return
    raise RequestStoppedError(RequestStopReason.REQUEST_CANCELLED)


def check_request_deadline(
    *, deadline_at: float | None, clock: Callable[[], float]
) -> None:
    """使用本轮的同一时钟检查期限，到达截止时刻即停止。

    未配置期限时直接返回；此检查不会中断正在进行的同步调用。
    """
    if deadline_at is None:
        return
    if clock() >= deadline_at:
        raise RequestStoppedError(RequestStopReason.REQUEST_DEADLINE_EXCEEDED)
