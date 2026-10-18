from dataclasses import dataclass
from typing import Any, Protocol

@dataclass(frozen=True)
class ConnectorStatus:
    provider: str
    configured: bool
    message: str

class SourceConnector(Protocol):
    def status(self) -> ConnectorStatus: ...
    async def fetch(self, **kwargs: Any) -> list[dict[str, Any]]: ...
