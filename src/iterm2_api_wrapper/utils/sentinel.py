from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from typing_extensions import Sentinel
else:
    from warnings import filterwarnings

    import typing_extensions

    filterwarnings(action="ignore", message="Subclassing sentinel is deprecated and will be disallowed in Python 3.15")

    class Sentinel(typing_extensions.sentinel):
        def __eq__(self, other):
            if not isinstance(other, (Sentinel, typing_extensions.sentinel)):
                return False
            return self.__name__ == other.__name__

        def __ne__(self, other):
            return not self.__eq__(other)

        def __bool__(self):
            """Return True to indicate that the sentinel is always truthy.

            .. example::
                .. code:: python
                MISSING = Sentinel("MISSING")
                if MISSING:
                    print("This will always print because MISSING is truthy.")
            """
            return bool(self.__name__)

        def __hash__(self):
            return hash(self.__name__)

        def __str__(self):
            return self.__name__

        def __repr__(self):
            return f"Sentinel<{self.__name__}>"


MISSING = Sentinel("MISSING")
