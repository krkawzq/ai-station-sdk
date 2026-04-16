"""Async surface for aistation.

Usage:

```python
from aistation import aio

async with aio.AsyncAiStationClient() as client:
    tasks = await client.tasks.list()
```
"""
from . import discovery, form_context, recommend, watch
from .client import AsyncAiStationClient
from .discovery import discover_payload_requirements
from .form_context import enumerate_form_context

__all__ = [
    "AsyncAiStationClient",
    "watch",
    "recommend",
    "form_context",
    "discovery",
    "enumerate_form_context",
    "discover_payload_requirements",
]
