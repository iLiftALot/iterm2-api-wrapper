from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .api.it2profile import PartialProfile, Profile


class ErrorMeta(type(BaseException)):
    msg: str
    __notes__: list[str] | None

    def __new__(
        cls: type[ErrorMeta], name: str, bases: tuple[type, ...], namespace: dict[str, Any], /, **kwds: Any
    ) -> ErrorMeta:
        namespace["msg"] = namespace.get("msg", kwds.get("msg", name))
        namespace["__module__"] = namespace.get("__module__", kwds.get("__module__", name))
        instance = super().__new__(cls, name, bases, namespace, **kwds)
        return instance


class iTermError(BaseException, metaclass=ErrorMeta):
    """Base error class for iTerm API errors."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.__module__ = self.__class__.__name__
        if sys.version_info >= (3, 11):
            self.add_note("\n\n*****NOTE*****\n\n" + self.msg.format(*args, **kwargs))
        else:
            note = "\n\n*****NOTE*****\n\n" + self.msg.format(*args, **kwargs)
            if getattr(self, "__notes__", None) is not None and isinstance(self.__notes__, list):
                self.__notes__.append(note)
            else:
                self.__notes__ = [note]


class ProfileNotFoundError(iTermError):
    msg = """
    Profile with name '{name}' not found. Available profiles:\n{profiles}
    """.strip()

    def __init__(
        self, *, target_profile_name: str, profile_data: dict[str, PartialProfile] | dict[str, Profile]
    ) -> None:
        super().__init__(
            name=target_profile_name, profiles="\n".join([f"- {name} ({p.guid})" for name, p in profile_data.items()])
        )


class WindowNotFoundError(iTermError):
    msg = """
    Window could not be found using profile '{name}'.
    """.strip()

    def __init__(self, name: str):
        super().__init__(name=name)


class TabNotFoundError(iTermError):
    msg = """
    Tab could not be found using profile '{name}'.
    """.strip()

    def __init__(self, name: str):
        super().__init__(name=name)


class SessionNotFoundError(iTermError):
    msg = """
    Session could not be found using '{name}'.
    """.strip()

    def __init__(self, name_or_guid: str):
        super().__init__(name=name_or_guid)
