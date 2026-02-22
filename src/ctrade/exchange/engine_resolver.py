"""Engine resolver — returns the correct trading engine based on current mode.

Reads the trading mode from RuntimeConfigStore and returns either PaperEngine
or LiveEngine.  Falls back to PaperEngine when live prerequisites are not met.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ctrade.exchange.live_engine import LiveEngine
    from ctrade.exchange.paper_engine import PaperEngine

logger = logging.getLogger(__name__)


def get_engine() -> PaperEngine | LiveEngine:
    """Return the active trading engine based on the current trading mode.

    Returns PaperEngine when:
    - Mode is "paper"
    - Mode is "live" but no exchange is configured (safety fallback)

    Returns LiveEngine when:
    - Mode is "live" and at least one exchange is configured
    """
    from ctrade.core.config_store import RuntimeConfigStore
    from ctrade.exchange.paper_engine import PaperEngine

    try:
        store = RuntimeConfigStore.get()
        mode = store.get_trading().get("mode", "paper")
    except RuntimeError:
        # Config store not initialized — default to paper
        return PaperEngine.get_instance()

    if mode == "live":
        # Check that at least one exchange is configured
        exchanges = store.list_exchanges()
        if exchanges:
            from ctrade.exchange.live_engine import LiveEngine

            return LiveEngine.get_instance()
        else:
            logger.warning(
                "Live mode requested but no exchange configured — falling back to paper engine"
            )
            return PaperEngine.get_instance()

    return PaperEngine.get_instance()
