"""Small, stable failure shapes shared by the CLI and gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CuffError(Exception):
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.context}
