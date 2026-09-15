"""Custom asynchronous enumerate helper"""

from typing import AsyncIterable, AsyncIterator, TypeVar


_Iterable_T = TypeVar("_Iterable_T")


async def async_enumerate(
    async_iterable: AsyncIterable[_Iterable_T], start: int = 0
) -> AsyncIterator[tuple[int, _Iterable_T]]:
    """Asynchronously enumerate an async generator or iterable."""
    count = start
    async for item in async_iterable:
        yield count, item
        count += 1
