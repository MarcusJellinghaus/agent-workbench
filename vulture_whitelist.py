"""Vulture whitelist - false positives and intentionally kept code.

This file tells Vulture to ignore items that appear unused but are
intentionally kept (framework hooks, pytest fixtures, entry points).

Format: _.attribute_name (Vulture's attribute-style whitelist syntax)

Review this list periodically - items may become used or truly dead over time.
"""
