"""Collector implementations.

Each module exposes a single class deriving from BaseCollector.
Registration via `register()` happens at import time.
"""
from .base import BaseCollector, CollectorError, HttpFetcher, register  # noqa: F401
from . import hackernews  # noqa: F401
from . import gdelt  # noqa: F401
from . import arxiv  # noqa: F401
from . import rss  # noqa: F401
from . import github_releases  # noqa: F401
from . import anthropic_sdk  # noqa: F401


def all_collectors():
    from .base import REGISTRY
    return list(REGISTRY.values())