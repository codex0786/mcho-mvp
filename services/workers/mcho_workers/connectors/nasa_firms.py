import os
from .base import ConnectorStatus

class NasaFirmsConnector:
    """Configuration guard only; hotspot ingestion is not implemented."""
    def status(self) -> ConnectorStatus:
        configured = bool(os.getenv("NASA_FIRMS_API_KEY"))
        return ConnectorStatus("nasa_firms", configured, "Key present; rate-limited ingestion adapter still requires implementation." if configured else "Disabled: API key absent.")
