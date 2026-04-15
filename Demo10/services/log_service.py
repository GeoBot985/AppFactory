from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    message: str


class LogService:
    def create_entry(self, message: str) -> LogEntry:
        stamp = datetime.now().strftime("%H:%M:%S")
        return LogEntry(timestamp=stamp, message=message)
