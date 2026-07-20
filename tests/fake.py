from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, cast

from iterm2_api_wrapper import state as state_module
from iterm2_api_wrapper.state import iTermState


if TYPE_CHECKING:
    from iterm2_api_wrapper.api.it2app import App
    from iterm2_api_wrapper.api.it2connection import Connection
    from iterm2_api_wrapper.api.it2profile import PartialProfile, Profile
    from iterm2_api_wrapper.api.it2session import Session
    from iterm2_api_wrapper.api.it2tab import Tab
    from iterm2_api_wrapper.api.it2window import Window
else:
    App = Connection = PartialProfile = Profile = Session = Tab = Window = object


class FakeNotificationResponse:
    class notification_response:
        import iterm2.api_pb2

        status = 0  # == iterm2.api_pb2.NotificationResponse.Status.Value("OK")
        _s = iterm2.api_pb2.NotificationResponse.Status.Value("OK")

    def HasField(self, field: str) -> bool:
        return False if field == "error" else True


class FakeConnection:
    def __init__(self, loop: asyncio.AbstractEventLoop | None = None, websocket: Any = None) -> None:
        self.loop = loop
        self.websocket = websocket

    async def async_send_message(self, *_) -> None:
        return

    async def async_dispatch_until_id(self, *_) -> FakeNotificationResponse:
        return FakeNotificationResponse()


class FakeWebsocket:
    def __init__(self, *, state: str = "OPEN", close_code: int | None = None) -> None:
        self.state = SimpleNamespace(name=state)
        self.close_code = close_code
        self.recv_calls = 0

    async def recv(self, *args: Any, **kwargs: Any) -> None:
        self.recv_calls += 1
        raise AssertionError("online() should not call recv()")


class FakeTarget:
    def __init__(self, **variables: str) -> None:
        self.variables = variables
        self.calls: list[str] = []

    async def async_get_variable(self, variable: str) -> str:
        self.calls.append(variable)
        return self.variables.get(variable, f"{variable}-value")


class FakeSession(FakeTarget):
    session_id = "session-1"

    def __init__(self, **variables: str) -> None:
        super().__init__(**variables)
        self.name = variables.get("name", "session-name")
        self.sent: list[tuple[str, bool]] = []
        self.contents: list[Any] = []
        self.line_info = SimpleNamespace(overflow=0, scrollback_buffer_height=0, mutable_area_height=0)

    async def async_send_text(self, text: str, *, suppress_broadcast: bool) -> None:
        self.sent.append((text, suppress_broadcast))

    async def async_get_line_info(self) -> Any:
        return self.line_info

    async def async_get_contents(self, first_line: int, number_of_lines: int) -> list[Any]:
        return self.contents[first_line : first_line + number_of_lines]

    async def async_set_name(self, name: str) -> None:
        self.name = name


class FakeTab(FakeTarget):
    def __init__(self, current_session: FakeSession | None = None, **variables: str) -> None:
        super().__init__(**variables)
        self.current_session = current_session
        self.title_set_to: str | None = None

    async def async_set_title(self, title: str) -> None:
        self.title_set_to = title
        self.variables["title"] = title


class FakePromptMonitor:
    Mode = state_module.PromptMonitor.Mode
    events: ClassVar[list[Any]] = []
    snapshots: ClassVar[list[list[str]]] = []
    instances: ClassVar[list[FakePromptMonitor]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.initial_snapshot = self._next_snapshot()
        FakePromptMonitor.instances.append(self)

    @classmethod
    def reset(cls, *, events: list[Any] | None = None, snapshots: list[list[str]] | None = None) -> None:
        cls.events = list(events or [])
        cls.snapshots = list(snapshots or [])
        cls.instances = []

    @classmethod
    def _next_snapshot(cls) -> list[str]:
        if cls.snapshots:
            return cls.snapshots.pop(0)
        return []

    async def __aenter__(self) -> FakePromptMonitor:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def async_get(self, *args: Any, **kwargs: Any) -> Any:
        if not FakePromptMonitor.events:
            raise TimeoutError
        event = FakePromptMonitor.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event

    async def refresh_snapshot(self) -> list[str]:
        return self._next_snapshot()


def as_connection(connection: object) -> Connection:
    return cast(Connection, connection)


def as_app(app: object) -> App:
    return cast(App, app)


def as_window(window: object) -> Window:
    return cast(Window, window)


def as_tab(tab: object) -> Tab:
    return cast(Tab, tab)


def as_session(session: object) -> Session:
    return cast(Session, session)


def as_profile(profile: object) -> Profile | PartialProfile:
    return cast(Profile | PartialProfile, profile)


def as_fake_connection(connection: Connection) -> FakeConnection:
    return cast(FakeConnection, connection)


def as_fake_session(session: Session) -> FakeSession:
    return cast(FakeSession, session)


def patch_attr(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def call_untyped(func: object, /, *args: object, **kwargs: object) -> Any:
    return cast(Any, func)(*args, **kwargs)


def make_state(loop: asyncio.AbstractEventLoop) -> iTermState:
    session = FakeSession(path="/current", username="user", hostname="host")
    profile = SimpleNamespace(name="Default", all_properties={})
    return iTermState(
        connection=as_connection(FakeConnection(loop=loop)),
        app=as_app(FakeTarget(global_var="global")),
        window=as_window(FakeTarget(window_var="window")),
        tab=as_tab(FakeTab(session, tab_var="tab", title="prompt$")),
        session=as_session(session),
        profile=as_profile(profile),
    )
