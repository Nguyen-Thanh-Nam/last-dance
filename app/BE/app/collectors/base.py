from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sqlite3


@dataclass
class CollectorContext:
    db: sqlite3.Connection
    project: dict[str, Any]
    run_id: str
    max_pages: int = 12
    max_depth: int = 2
    request_delay: float = 0.25


@dataclass
class CollectorResult:
    collector: str
    status: str = "ok"
    message: str = ""
    records_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class Collector:
    name = "base"

    def collect(self, context: CollectorContext) -> CollectorResult:
        raise NotImplementedError
