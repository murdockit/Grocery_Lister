from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

T = TypeVar("T")


async def with_retries(operation: Callable[[], Awaitable[T]], attempts: int = 3) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = await operation()
            if isinstance(result, httpx.Response) and result.status_code in {429, 500, 502, 503, 504}:
                result.raise_for_status()
            return result
        except httpx.HTTPStatusError as exc:
            last_error = exc
            response = exc.response
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == attempts:
                raise
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else attempt * 2.0
            await asyncio.sleep(delay)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt == attempts:
                raise
            await asyncio.sleep(attempt * 2.0)
    assert last_error is not None
    raise last_error
