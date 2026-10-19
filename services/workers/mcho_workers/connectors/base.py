"""Common connector contracts and capability/status descriptions."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ConnectorStatus:
    provider: str
    configured: bool
    message: str


class SourceConnector(Protocol):
    """Protocol for source adapters which expose discovery/fetch/normalization."""

    source_key: str

    async def discover(self, cursor: str | None) -> list[dict[str, Any]]: ...
    async def fetch(self, record: dict[str, Any]) -> bytes: ...
    async def normalize(self, raw: bytes, record: dict[str, Any]) -> dict[str, Any]: ...


class ConnectorNotConfigured(RuntimeError):
    """Raised when a connector is used without required approval/configuration."""
