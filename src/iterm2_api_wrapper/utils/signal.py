"""Run shell-side actions through an acknowledged Unix-signal protocol."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import os
import secrets
import shlex
import signal
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from ..state import iTermState


ShellType = Literal["zsh", "bash", "fish"] | str


@dataclass(frozen=True, slots=True)
class _SignalBinding:
    pid: int
    signal_number: signal.Signals
    handler_digest: str
    generation: str
    tty: str
    process_start: str


class Signal:
    """Change a target zsh session's directory through an acknowledged signal."""

    PROTOCOL_VERSION = "2"
    SIGNAL_SCRIPT = Path(__file__).parents[1] / "zsh" / "iterm2-signal-cd.zsh"
    SIGNAL_ROOT = Path.home() / ".iterm2" / "api-wrapper" / "signals"

    INSTALL_TIMEOUT = 2.0
    RESPONSE_TIMEOUT = 2.0
    POLL_INTERVAL = 0.01
    INSTALL_LOCK_TIMEOUT = 4.0

    BINDING_FILE = "binding"
    IDENTITY_FILE = "identity"
    INSTALL_LOCK_FILE = ".install.lock"

    def __init__(self, state: iTermState, shell: ShellType = "zsh") -> None:
        self.__state = state
        self.__shell: ShellType = Path(shell).name.lstrip("-")

    async def cd(self, path: str) -> None:
        """Change directory, bootstrapping the target shell only when required."""
        if self.__shell != "zsh":
            raise RuntimeError(f"Signal-driven directory changes require zsh; got {self.__shell!r}.")

        target = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(target):
            raise NotADirectoryError(target)

        signal_dir = self._prepare_signal_dir(self.__state.session.session_id)
        handler_digest = self._handler_digest()

        # Multiple CLI processes may target the same iTerm2 session. Only one
        # process may decide/install the handler at a time. Once installed,
        # normal signal dispatch does not hold this lock.
        async with self._installation_lock(signal_dir):
            binding = await self._get_or_install_binding(
                signal_dir,
                handler_digest,
            )

        request_nonce = secrets.token_hex(16)
        request_path = signal_dir / f"request.{binding.pid}.{request_nonce}"
        response_path = signal_dir / f"response.{binding.pid}.{request_nonce}"

        try:
            self._atomic_write(
                request_path,
                os.fsencode(target) + b"\0",
            )

            try:
                os.kill(
                    binding.pid,
                    binding.signal_number,
                )
            except (
                PermissionError,
                ProcessLookupError,
            ) as error:
                self._invalidate_binding(signal_dir)
                raise RuntimeError(f"The target zsh process {binding.pid} is no longer signalable.") from error

            try:
                response = await self._wait_for_file(
                    response_path,
                    self.RESPONSE_TIMEOUT,
                )
            except TimeoutError:
                # The shell did not prove that the cached trap handled the
                # request. Never reuse that binding without reinstalling.
                self._invalidate_binding(signal_dir)
                raise

            self._validate_response(
                response,
                binding.pid,
                request_nonce,
            )
        finally:
            request_path.unlink(missing_ok=True)
            response_path.unlink(missing_ok=True)

    async def _get_or_install_binding(
        self,
        signal_dir: Path,
        handler_digest: str,
    ) -> _SignalBinding:
        binding_path = signal_dir / self.BINDING_FILE
        identity_path = signal_dir / self.IDENTITY_FILE

        binding = self._read_cached_binding(
            binding_path,
            identity_path,
            handler_digest,
        )

        if binding is not None:
            validated = await self._validated_target_binding(binding)
            if validated is not None:
                return validated

        self._invalidate_binding(signal_dir)

        binding = await self._install(
            signal_dir,
            handler_digest,
        )
        validated = await self._validated_target_binding(binding)

        if validated is None:
            self._invalidate_binding(signal_dir)
            raise RuntimeError("The installed signal handler does not belong to the target iTerm2 session.")

        # The shell publishes whether the trap is currently ready. Python
        # records the process identity it independently observed. A cached
        # binding is reusable only when both records still agree.
        self._write_identity(
            identity_path,
            validated,
        )

        return validated

    async def _install(
        self,
        signal_dir: Path,
        handler_digest: str,
    ) -> _SignalBinding:
        if not self.SIGNAL_SCRIPT.is_file():
            raise FileNotFoundError(f"Packaged signal handler not found: {self.SIGNAL_SCRIPT}")

        install_nonce = secrets.token_hex(16)
        ack_path = signal_dir / f"install.{install_nonce}"

        command = " ".join(
            (
                "builtin source",
                shlex.quote(str(self.SIGNAL_SCRIPT)),
                shlex.quote(str(signal_dir)),
                shlex.quote(install_nonce),
                shlex.quote(handler_digest),
            )
        )

        try:
            # async_send_text acknowledges delivery to iTerm2, not execution by
            # zsh. The install file is the actual completion boundary.
            await self.__state._send_text(
                command,
                suppress=True,
            )

            payload = await self._wait_for_file(
                ack_path,
                self.INSTALL_TIMEOUT,
            )

            return self._parse_install_ack(
                payload,
                install_nonce,
                handler_digest,
            )
        finally:
            ack_path.unlink(missing_ok=True)

    async def _validated_target_binding(
        self,
        binding: _SignalBinding,
    ) -> _SignalBinding | None:
        try:
            self._assert_process_alive(binding.pid)

            target_tty = self._normalize_tty(str(await self.__state.get_session_var("tty")))

            (
                process_tty,
                process_start,
                process_name,
            ) = await asyncio.to_thread(
                self._read_process_identity,
                binding.pid,
            )
        except (
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
            ValueError,
        ):
            return None

        # The PID must still be a zsh on the exact TTY owned by the selected
        # iTerm2 session. This prevents a stale PID from targeting a process
        # belonging to another session.
        if target_tty != process_tty or Path(process_name).name.lstrip("-") != "zsh":
            return None

        # Cached bindings additionally carry the process-start identity. A
        # recycled PID—even one that now happens to be another zsh on the same
        # TTY—will not match.
        if binding.tty and self._normalize_tty(binding.tty) != process_tty:
            return None

        if binding.process_start and self._normalize_whitespace(binding.process_start) != process_start:
            return None

        return replace(
            binding,
            tty=process_tty,
            process_start=process_start,
        )

    @classmethod
    def _read_cached_binding(
        cls,
        binding_path: Path,
        identity_path: Path,
        handler_digest: str,
    ) -> _SignalBinding | None:
        if binding_path.is_symlink() or identity_path.is_symlink():
            return None

        try:
            binding_fields = binding_path.read_text(encoding="utf-8").rstrip("\n").split("\t")
            identity_fields = identity_path.read_text(encoding="utf-8").rstrip("\n").split("\t")
        except (
            FileNotFoundError,
            OSError,
        ):
            return None

        try:
            if len(binding_fields) != 6 or len(identity_fields) != 8:
                return None

            (
                version,
                status,
                pid_text,
                signal_name,
                received_digest,
                generation,
            ) = binding_fields

            (
                identity_version,
                identity_status,
                *identity_values,
            ) = identity_fields

            if (
                version != cls.PROTOCOL_VERSION
                or status != "ready"
                or identity_version != cls.PROTOCOL_VERSION
                or identity_status != "cached"
                or received_digest != handler_digest
                or identity_values[:4]
                != [
                    pid_text,
                    signal_name,
                    received_digest,
                    generation,
                ]
            ):
                return None

            return cls._binding_from_fields(
                pid_text=pid_text,
                signal_name=signal_name,
                handler_digest=received_digest,
                generation=generation,
                tty=identity_values[4],
                process_start=identity_values[5],
            )
        except RuntimeError:
            return None

    @classmethod
    def _parse_install_ack(
        cls,
        payload: bytes,
        nonce: str,
        handler_digest: str,
    ) -> _SignalBinding:
        fields = payload.decode("utf-8").rstrip("\n").split("\t", 6)

        if len(fields) < 6:
            raise RuntimeError("Malformed signal-install acknowledgment.")

        (
            version,
            status,
            pid_text,
            signal_name,
            received_nonce,
            received_digest,
        ) = fields[:6]

        if version != cls.PROTOCOL_VERSION:
            raise RuntimeError(f"Unsupported signal protocol version: {version!r}.")

        if received_nonce != nonce:
            raise RuntimeError("Signal-install acknowledgment nonce mismatch.")

        if received_digest != handler_digest:
            raise RuntimeError("Signal-install acknowledgment handler mismatch.")

        if status != "ok":
            detail = fields[6] if len(fields) >= 7 else "unknown shell installation failure"
            raise RuntimeError(f"Unable to install shell signal handler: {detail}")

        if len(fields) != 6:
            raise RuntimeError("Malformed successful signal-install acknowledgment.")

        return cls._binding_from_fields(
            pid_text=pid_text,
            signal_name=signal_name,
            handler_digest=received_digest,
            generation=nonce,
            tty="",
            process_start="",
        )

    @classmethod
    def _binding_from_fields(
        cls,
        *,
        pid_text: str,
        signal_name: str,
        handler_digest: str,
        generation: str,
        tty: str,
        process_start: str,
    ) -> _SignalBinding:
        try:
            pid = int(pid_text)
            signal_number = signal.Signals(
                getattr(
                    signal,
                    f"SIG{signal_name}",
                )
            )
        except (
            AttributeError,
            KeyError,
            ValueError,
        ) as error:
            raise RuntimeError("Malformed PID or signal in shell binding.") from error

        if (
            pid <= 0
            or signal_name not in {"USR1", "USR2"}
            or not cls._is_hex(
                handler_digest,
                length=64,
            )
            or not cls._is_hex(
                generation,
                length=32,
            )
        ):
            raise RuntimeError("Unsafe shell signal binding.")

        return _SignalBinding(
            pid=pid,
            signal_number=signal_number,
            handler_digest=handler_digest,
            generation=generation,
            tty=tty,
            process_start=process_start,
        )

    @staticmethod
    def _is_hex(
        value: str,
        *,
        length: int,
    ) -> bool:
        if len(value) != length:
            return False

        try:
            bytes.fromhex(value)
        except ValueError:
            return False

        return True

    @classmethod
    def _write_identity(
        cls,
        path: Path,
        binding: _SignalBinding,
    ) -> None:
        payload = "\t".join(
            (
                cls.PROTOCOL_VERSION,
                "cached",
                str(binding.pid),
                binding.signal_number.name.removeprefix("SIG"),
                binding.handler_digest,
                binding.generation,
                binding.tty,
                binding.process_start,
            )
        )

        cls._atomic_write(
            path,
            payload.encode("utf-8") + b"\n",
        )

    @classmethod
    def _invalidate_binding(
        cls,
        signal_dir: Path,
    ) -> None:
        (signal_dir / cls.BINDING_FILE).unlink(missing_ok=True)
        (signal_dir / cls.IDENTITY_FILE).unlink(missing_ok=True)

    @classmethod
    @asynccontextmanager
    async def _installation_lock(
        cls,
        signal_dir: Path,
    ) -> AsyncIterator[None]:
        lock_path = signal_dir / cls.INSTALL_LOCK_FILE
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(
            lock_path,
            flags,
            0o600,
        )
        acquired = False

        try:
            os.fchmod(
                descriptor,
                0o600,
            )

            loop = asyncio.get_running_loop()
            deadline = loop.time() + cls.INSTALL_LOCK_TIMEOUT

            while True:
                try:
                    fcntl.flock(
                        descriptor,
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                    acquired = True
                    break
                except BlockingIOError:
                    if loop.time() >= deadline:
                        raise TimeoutError(f"Timed out waiting for the signal installer lock: {lock_path}") from None

                    await asyncio.sleep(cls.POLL_INTERVAL)

            yield
        finally:
            if acquired:
                fcntl.flock(
                    descriptor,
                    fcntl.LOCK_UN,
                )

            os.close(descriptor)

    @classmethod
    def _handler_digest(cls) -> str:
        if not cls.SIGNAL_SCRIPT.is_file():
            raise FileNotFoundError(f"Packaged signal handler not found: {cls.SIGNAL_SCRIPT}")

        return hashlib.sha256(cls.SIGNAL_SCRIPT.read_bytes()).hexdigest()

    @staticmethod
    def _read_process_identity(
        pid: int,
    ) -> tuple[str, str, str]:
        def ps_field(field: str) -> str:
            completed = subprocess.run(
                [
                    "/bin/ps",
                    "-p",
                    str(pid),
                    "-o",
                    f"{field}=",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            value = completed.stdout.strip()
            if not value:
                raise RuntimeError(f"Process {pid} has no {field} value.")

            return value

        return (
            Signal._normalize_tty(ps_field("tty")),
            Signal._normalize_whitespace(ps_field("lstart")),
            ps_field("comm"),
        )

    @staticmethod
    def _normalize_tty(value: str) -> str:
        return value.strip().removeprefix("/dev/")

    @staticmethod
    def _normalize_whitespace(
        value: str,
    ) -> str:
        return " ".join(value.split())

    @classmethod
    def _prepare_signal_dir(
        cls,
        session_id: str,
    ) -> Path:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        session_dir = cls.SIGNAL_ROOT / digest

        for directory in (
            cls.SIGNAL_ROOT,
            session_dir,
        ):
            if directory.is_symlink():
                raise RuntimeError(f"Refusing to use symlinked signal directory: {directory}")

            directory.mkdir(
                parents=True,
                exist_ok=True,
                mode=0o700,
            )

            if not directory.is_dir():
                raise NotADirectoryError(directory)

            directory.chmod(0o700)

        return session_dir

    @classmethod
    async def _wait_for_file(
        cls,
        path: Path,
        timeout: float,
    ) -> bytes:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            try:
                return path.read_bytes()
            except FileNotFoundError:
                if loop.time() >= deadline:
                    raise TimeoutError(f"Timed out waiting for shell acknowledgment: {path.name}") from None

                await asyncio.sleep(cls.POLL_INTERVAL)

    @staticmethod
    def _atomic_write(
        path: Path,
        payload: bytes,
    ) -> None:
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(
            temporary,
            flags,
            0o600,
        )

        try:
            with os.fdopen(
                descriptor,
                "wb",
            ) as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())

            os.replace(
                temporary,
                path,
            )
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _validate_response(
        cls,
        payload: bytes,
        pid: int,
        nonce: str,
    ) -> None:
        fields = payload.decode("utf-8").rstrip("\n").split("\t")

        if len(fields) != 7:
            raise RuntimeError("Malformed signal response acknowledgment.")

        (
            version,
            status,
            pid_text,
            received_nonce,
            cd_status,
            prompt_status,
            redraw_status,
        ) = fields

        if version != cls.PROTOCOL_VERSION or status != "ok":
            raise RuntimeError("Shell returned an unsupported signal response.")

        if pid_text != str(pid) or received_nonce != nonce:
            raise RuntimeError("Signal response identity mismatch.")

        try:
            statuses = tuple(
                int(value)
                for value in (
                    cd_status,
                    prompt_status,
                    redraw_status,
                )
            )
        except ValueError as error:
            raise RuntimeError("Signal response contains a malformed status.") from error

        if statuses[0] != 0:
            raise RuntimeError(f"The target shell could not change directory (status={statuses[0]}).")

        if statuses[1] != 0:
            raise RuntimeError(f"A precmd hook failed while refreshing the prompt (status={statuses[1]}).")

        if statuses[2] != 0:
            raise RuntimeError(f"ZLE failed to redraw the prompt (status={statuses[2]}).")

    @staticmethod
    def _assert_process_alive(pid: int) -> None:
        try:
            # Signal 0 checks existence and permission without delivering a
            # real signal.
            os.kill(pid, 0)
        except (
            PermissionError,
            ProcessLookupError,
        ) as error:
            raise RuntimeError(f"The acknowledged zsh process {pid} is no longer available.") from error
