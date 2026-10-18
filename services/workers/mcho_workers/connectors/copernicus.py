import os
from .base import ConnectorStatus

class CopernicusConnector:
    """Configuration guard only; catalog/download workflow is not implemented."""
    def status(self) -> ConnectorStatus:
        configured = bool(os.getenv("COPERNICUS_CLIENT_ID") and os.getenv("COPERNICUS_CLIENT_SECRET"))
        return ConnectorStatus("copernicus", configured, "Credentials present; ingestion adapter still requires implementation." if configured else "Disabled: credentials absent.")
