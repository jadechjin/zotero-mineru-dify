"""轻量事件总线 — 任务内部的事件发布回调机制。"""

from typing import Callable


EventCallback = Callable[[str, str, str, str], None]
"""签名: (level, stage, event, message) -> None"""


class EventBus:
    """简易事件总线，支持订阅/发布。

    主要用于 PipelineRunner 内部把日志事件推送到 Task 对象。
    """

    def __init__(self):
        self._listeners: list[EventCallback] = []

    def subscribe(self, callback: EventCallback):
        self._listeners.append(callback)

    def unsubscribe(self, callback: EventCallback):
        self._listeners = [cb for cb in self._listeners if cb is not callback]

    def emit(self, level: str, stage: str, event: str, message: str):
        for cb in self._listeners:
            try:
                cb(level, stage, event, message)
            except Exception:
                pass
