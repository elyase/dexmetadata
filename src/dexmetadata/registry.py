"""
Registry for pool handlers and identifier categorization.
"""

import logging
from typing import Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class PoolHandlerRegistry:
    """Registry of pool metadata handlers."""

    def __init__(self):
        self.handlers = []

    def register(self, handler_class) -> None:
        """Register a pool handler class."""
        self.handlers.append(handler_class)

    def get_handler_for(self, identifier: str):
        """Get the appropriate handler class for a pool identifier."""
        for handler_class in self.handlers:
            if handler_class.supports(identifier):
                return handler_class
        return None

    def categorize_identifiers(self, pool_identifiers: List[str]) -> Dict:
        """Categorize pool identifiers by their handler types."""
        categorized = {}
        for identifier in pool_identifiers:
            handler_class = self.get_handler_for(identifier)
            if handler_class:
                if handler_class not in categorized:
                    categorized[handler_class] = []
                categorized[handler_class].append(identifier)
            else:
                logger.warning(f"No handler found for identifier: {identifier}")
        return categorized


# Initialize the global handler registry
pool_handler_registry = PoolHandlerRegistry()
