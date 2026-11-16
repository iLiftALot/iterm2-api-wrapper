from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from typing_extensions import ParamSpec


_P = ParamSpec("_P")
_R = TypeVar("_R")


async def to_thread(func: Callable[_P, _R], /, *args: _P.args, **kwargs: _P.kwargs) -> _R:
    return await asyncio.to_thread(func, *args, **kwargs)


class AsyncPath(Path):
    def __new__(cls, *args: str | os.PathLike, **kwargs: object) -> AsyncPath:
        instance = super().__new__(cls, *args, **kwargs)
        return instance

    async def aresolve(self) -> AsyncPath:
        return await to_thread(self.resolve, strict=False)

    async def async_absolute(self) -> AsyncPath:
        return await to_thread(self.absolute)

    async def aexpanduser(self) -> AsyncPath:
        return await to_thread(self.expanduser)

    async def ais_dir(self) -> bool:
        return await to_thread(self.is_dir)

    async def aexists(self) -> bool:
        return await to_thread(self.exists)

    async def aread_bytes(self) -> bytes:
        return await to_thread(self.read_bytes)

    def string(self) -> str:
        return str(self)
