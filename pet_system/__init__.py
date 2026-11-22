"""Pawk1ns pet system package.

Stage 3 extracts the time-driven pet statistic engine out of the ``main.py``
monolith into this package so it can be shared by the bot, the Mini App and
``unified_storage.py`` without depending on the ``main`` global namespace.

The package is intentionally dependency-light (standard library only) and never
imports ``main`` or ``unified_storage``; this keeps the import graph acyclic.
"""

from __future__ import annotations

from .pet_stats import update_pet_stats_with_time

__all__ = ["update_pet_stats_with_time"]
