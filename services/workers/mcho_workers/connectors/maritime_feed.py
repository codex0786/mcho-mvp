import os
from .base import ConnectorStatus

class MaritimeFeedConnector:
    """Licensed-provider guard; intentionally does not fetch live vessel positions."""
    def status(self) -> ConnectorStatus:
        configured = bool(os.getenv("MARITIME_PROVIDER") and os.getenv("MARITIME_API_KEY"))
        return ConnectorStatus("licensed_maritime_aggregate", configured, "Provider named; aggregation adapter still requires implementation." if configured else "Disabled: provider/key absent.")
