from __future__ import annotations

import os
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    ItemsView,
    Iterable,
    Iterator,
    KeysView,
    Protocol,
    TypeVar,
    ValuesView,
    cast,
    overload,
)

from iterm2_api_wrapper.utils.sentinel import MISSING


if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem


UnknownDefaultValueT = TypeVar("UnknownDefaultValueT")
ProvidedDefaultT = TypeVar("ProvidedDefaultT")

_KeyT = TypeVar("_KeyT")
_ValueT = TypeVar("_ValueT")
_ValueT_co = TypeVar("_ValueT_co", covariant=True)


class IterableSupportsItems(Protocol[_KeyT, _ValueT_co]):
    def items(self) -> ItemsView[_KeyT, _ValueT_co]: ...

    def __getitem__(self, key: _KeyT, /) -> _ValueT_co: ...

    def __contains__(self, key: str, /) -> bool: ...

    def __iter__(self) -> Iterator[_KeyT]: ...


class _EnvMeta(type):
    """Metaclass for Env to allow class-level environment variable manipulation."""

    key: str
    _value: Any = MISSING
    _env: os._Environ[str] = os.environ

    def __getitem__(cls, key: str) -> str | None:
        """Get an environment variable at the class level.

        .. example::
            .. code:: python
            value = Env["MY_ENV_VAR"]
        """
        return cls._env.get(key)

    def __setitem__(cls, key: str, value: Any) -> None:
        """Set an environment variable, converting its value to a string.

        .. example::
            .. code:: python
            Env["MY_ENV_VAR"] = "value"
        """
        cls._env[key] = str(value)

    def __delitem__(cls, key: str) -> None:
        """Delete an environment variable at the class level.

        .. example::
            .. code:: python
            del Env["MY_ENV_VAR"]
        """
        if hasattr(cls, "key") and cls.key == key:
            cls._value = MISSING

        if key in cls._env:
            del cls._env[key]

    def __contains__(cls, key: object) -> bool:
        return key in cls._env

    def __iter__(cls) -> Iterator[str]:
        keys = list(cls._env)
        yield from keys

    def __len__(cls) -> int:
        return len(cls._env)

    @overload
    def get(cls, key: str, default: MISSING = MISSING) -> str | None: ...
    @overload
    def get(cls, key: str, default: UnknownDefaultValueT) -> str | UnknownDefaultValueT: ...
    def get(cls, key: str, default: UnknownDefaultValueT | MISSING = MISSING) -> str | UnknownDefaultValueT | None:
        """Retrieve the value of an environment variable with an optional default."""
        return cls._env.get(key, default if default is not MISSING else None)

    @overload
    def pop(cls, key: str, default: MISSING = MISSING) -> str | None: ...
    @overload
    def pop(cls, key: str, default: str) -> str: ...
    @overload
    def pop(cls, key: str, default: ProvidedDefaultT) -> str | ProvidedDefaultT: ...
    def pop(cls, key: str, default: UnknownDefaultValueT | MISSING = MISSING) -> str | UnknownDefaultValueT | None:
        """Remove an environment variable at the class level and return its value, or the default if not set."""

        if hasattr(cls, "key") and key == cls.key:
            cls._value = MISSING

        return cls._env.pop(key, default if default is not MISSING else None)

    def items(cls) -> ItemsView[str, str]:
        """Return a view of the environment variables at the class level."""
        return cls._env.items()

    def keys(cls) -> KeysView[str]:
        """Return a view of the environment variable keys at the class level."""
        return cls._env.keys()

    def values(cls) -> ValuesView[str]:
        """Return a view of the environment variable values at the class level."""
        return cls._env.values()

    @overload
    def update(cls, m: SupportsKeysAndGetItem[_KeyT, _ValueT], /) -> None: ...
    @overload
    def update(cls, m: SupportsKeysAndGetItem[str, _ValueT], /, **kwargs: _ValueT) -> None: ...
    @overload
    def update(cls, m: Iterable[tuple[_KeyT, _ValueT]], /) -> None: ...
    @overload
    def update(cls, m: Iterable[tuple[str, _ValueT]], /, **kwargs: _ValueT) -> None: ...
    @overload
    def update(cls, /, **kwargs) -> None: ...
    def update(cls, m, **kwargs) -> None:
        cls._env.update(m, **kwargs)

        if hasattr(cls, "key") and cls.key in m:
            cls._value = str(m[cls.key])

        if hasattr(cls, "key") and cls.key in kwargs:
            cls._value = str(kwargs[cls.key])

    def copy(cls) -> dict[str, str]:
        return cls._env.copy()


class Env(Generic[UnknownDefaultValueT], metaclass=_EnvMeta):
    """Utility class for environment-related checks."""

    key: str
    default: UnknownDefaultValueT

    _env = os.environ
    _value: UnknownDefaultValueT | MISSING

    @overload
    def __init__(self: Env[None], key: str, default: MISSING = ...) -> None: ...
    @overload
    def __init__(self: Env[ProvidedDefaultT], key: str, default: ProvidedDefaultT) -> None: ...
    def __init__(self, key: str, default: UnknownDefaultValueT | MISSING | None = MISSING) -> None:
        self.key = key
        # The overloads restrict an omitted default to Env[str, None].
        self.default = cast(UnknownDefaultValueT, default if default is not MISSING else None)
        self._value = MISSING

    @property
    def value(self) -> str | UnknownDefaultValueT:
        """Retrieve the value of the environment variable, or the default if not set."""
        if self._value is MISSING:
            self._value = cast(UnknownDefaultValueT, self._env.get(self.key, self.default))
        return self._value

    def isTrue(self) -> bool:
        """Check if the environment variable is set to a truthy value."""
        value = self.value
        return bool(value) and str(value).lower() in ("1", "true")

    def isFalse(self) -> bool:
        """Check if the environment variable is set to a falsy value."""
        value = self.value
        return not bool(value) or str(value).lower() in ("0", "false")

    @staticmethod
    def isProd() -> bool:
        """Determine if the current environment is production based on environment variables."""
        return Env.get("ENV", "development").lower() in ("production", "prod")

    @staticmethod
    def isDev() -> bool:
        """Determine if the current environment is development based on environment variables."""
        return Env.get("ENV", "development").lower() in ("development", "dev")

    def __str__(self) -> str:
        """Return the string representation of the environment variable's value."""
        return str(self.value)

    def __repr__(self) -> str:
        """Return a detailed string representation of the environment variable object."""
        return f"Env(key={self.key!r}, default={self.default!r}, value={self._value!r})"


if __name__ == "__main__":
    env_get = Env.get("ENV", "<NONE>")
    pp = Env["ENV"]
    Env["ENV"] = "development"
    pp2 = Env["ENV"]
    pp3 = Env.pop("ENV", "2")
    pp4 = "ENV" in Env
    pp5 = Env.get("ENV")
    Env["ENV"] = "prod"
    pp6 = Env["ENV"]
    del Env["ENV"]
    pp6_val = Env.get("ENV", "<NONE>")
    pp7 = "ENV" in Env
    pp8 = len(list(Env.keys()))
    pp9 = len(list(Env.values()))
    Env.update({"ENV": "update_from_test"})
    pp10 = Env.get("ENV")
    pp11 = "ENV" in Env.copy()
    pp12 = dict(Env) == Env.copy()
    pp13 = Env.items()

    print(f"""

    Env.get("ENV", "<NONE>") -> {env_get}
    Env["ENV"] -> {pp}

** after Env["ENV"] -> "development" **

    Env["ENV"] -> {pp2}
    Env.pop("ENV", "2") -> {pp3}
    "ENV" in Env -> {pp4}

** after Env.pop("ENV") **
    Env.get("ENV") -> {pp5}

** after del Env["ENV"] **
    "ENV" in Env -> {pp7} ({pp6} -> {pp6_val})

len(Env.keys()) -> {pp8}
len(Env.values()) -> {pp9}

** after Env.update({{"ENV": "update_from_test"}}) **
    Env.get("ENV") -> {pp10}

"ENV" in Env.copy() -> {pp11}
dict(Env) == Env.copy() -> {pp12}


Env.items() -> {pp13}

len(Env) -> {len(Env)}
""")
