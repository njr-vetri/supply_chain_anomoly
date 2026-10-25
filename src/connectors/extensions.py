"""Explicit integration catalog: mocks are simulated, enterprise adapters are extensions."""
from datetime import datetime, timezone

from src.connectors.base import ConnectorHealth


class SimulatedConnector:
    """A test/demo adapter whose outputs must always be marked SIMULATED."""
    label = "SIMULATED"

    def __init__(self, name: str = "simulated"):
        self.name = name

    def health_check(self):
        return ConnectorHealth(self.name, "SIMULATED", datetime.now(timezone.utc).isoformat(),
                               "mock connector; no external system was contacted")

    def read_batches(self):
        return iter(())


UNBUILT_CONNECTOR_EXTENSIONS = {
    "erp": {"status": "EXTENSION_NOT_IMPLEMENTED", "requires": "vendor-specific adapter and mapping"},
    "wms": {"status": "EXTENSION_NOT_IMPLEMENTED", "requires": "vendor-specific adapter and mapping"},
}
