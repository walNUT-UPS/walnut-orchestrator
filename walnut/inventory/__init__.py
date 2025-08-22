"""
Inventory and capability indexing for the walNUT Policy System.

This package provides fast inventory refresh and capability indexing
for policy target resolution and dry-run operations.
"""

from .index import (
    InventoryIndex,
    create_inventory_index,
    quick_capability_check,
    resolve_target_selector,
)

__all__ = [
    "InventoryIndex",
    "create_inventory_index", 
    "quick_capability_check",
    "resolve_target_selector",
]