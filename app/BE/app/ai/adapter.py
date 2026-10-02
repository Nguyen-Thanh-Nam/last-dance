from __future__ import annotations

from typing import Any, Protocol

from ..schemas import ModelOutput


class AIAdapter(Protocol):
    name: str

    def analyze(self, project: dict[str, Any], sources: list[dict[str, Any]], assets: list[dict[str, Any]]) -> ModelOutput:
        ...
