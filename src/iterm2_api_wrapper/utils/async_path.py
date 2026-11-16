from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import PosixPath, PurePath
from typing import TypeVar

from typing_extensions import ParamSpec


_P = ParamSpec("_P")
_R = TypeVar("_R")


async def to_thread(func: Callable[_P, _R], /, *args: _P.args, **kwargs: _P.kwargs) -> _R:
    return await asyncio.to_thread(func, *args, **kwargs)


class AsyncPath(PosixPath, PurePath):
    async def aresolve(self) -> AsyncPath:
        return await to_thread(self.resolve, strict=False)

    async def async_absolute(self) -> AsyncPath:
        return await to_thread(self.absolute)

    async def aexpanduser(self) -> AsyncPath:
        return await to_thread(self.expanduser)

    def expanduser(self) -> AsyncPath:
        return super().expanduser()

    async def ais_dir(self) -> bool:
        return await to_thread(self.is_dir)

    async def aexists(self) -> bool:
        return await to_thread(self.exists)

    async def aread_bytes(self) -> bytes:
        return await to_thread(self.read_bytes)

    async def aread_text(self, encoding: str | None = None, errors: str | None = None) -> str:
        return await to_thread(self.read_text, encoding=encoding, errors=errors)

    @classmethod
    def home(cls) -> AsyncPath:
        return AsyncPath(os.path.expanduser("~"))

    def string(self) -> str:
        return str(self)
