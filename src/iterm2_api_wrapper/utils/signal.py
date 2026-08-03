"""Run parent-shell commands through an acknowledged Unix-signal protocol."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import os
import secrets
import shlex
import signal
import subprocess
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from ..state import iTermState


ShellType = Literal["zsh", "bash", "fish"] | str


@dataclass(frozen=True, slots=True)
class SignalResult:
    """Captured result from a command executed in the target parent shell."""

    returncode: int
    stdout: str
    stderr: str


class SignalShellBusyError(RuntimeError):
    """Raised when installing would type into a non-shell foreground job."""


@dataclass(frozen=True, slots=True)
class _SignalBinding:
    pid: int
    signal_number: signal.Signals
    handler_digest: str
    generation: str
    tty: str
    process_start: str


class Signal:
    """Execute trusted, noninteractive commands in a target Zsh session."""

    PROTOCOL_VERSION = "3"
    SIGNAL_SCRIPT = Path(__file__).parents[1] / "zsh" / "iterm2-signal.zsh"
    SIGNAL_ROOT = Path.home() / ".iterm2" / "api-wrapper" / "signals"

    INSTALL_TIMEOUT = 5.0
    START_TIMEOUT = 5.0
    POLL_INTERVAL = 0.01
    INSTALL_LOCK_TIMEOUT = 5.0

    BINDING_FILE = "binding"
    BUSY_FILE = "busy"
    IDENTITY_FILE = "identity"
    INSTALL_LOCK_FILE = ".install.lock"
    OPERATION_LOCK_FILE = ".operation.lock"
    REQUEST_ARTIFACT_PREFIXES = ("request", "started", "response", "stdout", "stderr")

    def __init__(self, state: iTermState, shell: ShellType = "zsh") -> None:
        self.__state = state
        self.__shell = self._shell_name(shell)

    @classmethod
    def supports(cls, shell: ShellType) -> bool:
        """Return whether this protocol supports ``shell``."""
        return cls._shell_name(shell) == "zsh"

    async def install(self) -> None:
        """Install or validate the target shell's reusable signal handler."""
        self._require_supported_shell()
        signal_dir = self._prepare_signal_dir(self.__state.session.session_id)
        handler_digest = self._handler_digest()

        async with self._operation_lock(signal_dir), self._installation_lock(signal_dir):
            await self._get_or_install_binding(signal_dir, handler_digest, wait_for_ready=False)

    async def execute(self, command: str) -> SignalResult:
        """Execute ``command`` out-of-band in the target interactive Zsh.

        The command runs synchronously in the parent shell so shell-local state
        changes can persist. Its stdin is ``/dev/null`` and stdout/stderr are
        captured instead of being written to the target terminal.
        """
        if "\0" in command:
            raise ValueError("Signal commands cannot contain NUL bytes.")

        self._require_supported_shell()
        signal_dir = self._prepare_signal_dir(self.__state.session.session_id)
        handler_digest = self._handler_digest()

        # The binding is deliberately withdrawn while the parent shell is
        # executing a request. Serializing the full operation prevents another
        # process from mistaking that temporary state for a missing handler and
        # injecting a second installation command into the busy shell.
        async with self._operation_lock(signal_dir):
            async with self._installation_lock(signal_dir):
                binding = await self._get_or_install_binding(signal_dir, handler_digest, wait_for_ready=True)

            self._cleanup_request_artifacts(signal_dir)
            return await self._execute_request(signal_dir, binding, command)

    async def _execute_request(self, signal_dir: Path, binding: _SignalBinding, command: str) -> SignalResult:
        request_nonce = secrets.token_hex(16)
        request_path = signal_dir / f"request.{binding.pid}.{request_nonce}"
        started_path = signal_dir / f"started.{binding.pid}.{request_nonce}"
        response_path = signal_dir / f"response.{binding.pid}.{request_nonce}"
        stdout_path = signal_dir / f"stdout.{binding.pid}.{request_nonce}"
        stderr_path = signal_dir / f"stderr.{binding.pid}.{request_nonce}"
        request_paths = (request_path, started_path, response_path, stdout_path, stderr_path)

        try:
            self._atomic_write(stdout_path, b"")
            self._atomic_write(stderr_path, b"")
            self._atomic_write(request_path, command.encode("utf-8"))

            try:
                os.kill(binding.pid, binding.signal_number)
            except (PermissionError, ProcessLookupError) as error:
                self._invalidate_binding(signal_dir)
                raise RuntimeError(f"The target zsh process {binding.pid} is no longer signalable.") from error

            try:
                started = await self._wait_for_file(started_path, self.START_TIMEOUT, process_pid=binding.pid)
                self._validate_started(started, binding.pid, request_nonce)
            except (RuntimeError, TimeoutError):
                # No start acknowledgment means the cached trap did not prove
                # ownership of this request. It must not be reused.
                self._invalidate_binding(signal_dir)
                raise

            try:
                response = await self._wait_for_file(response_path, None, process_pid=binding.pid)
                command_status, prompt_status, redraw_status = self._parse_response(
                    response, binding.pid, request_nonce
                )
                await self._wait_until_not_busy(signal_dir, binding.pid)
            except RuntimeError:
                self._invalidate_binding(signal_dir)
                raise

            result = SignalResult(
                returncode=command_status,
                stdout=stdout_path.read_bytes().decode("utf-8", errors="replace"),
                stderr=stderr_path.read_bytes().decode("utf-8", errors="replace"),
            )

            self._raise_refresh_errors(prompt_status, redraw_status)
            return result
        finally:
            for path in request_paths:
                path.unlink(missing_ok=True)

    async def _get_or_install_binding(
        self, signal_dir: Path, handler_digest: str, *, wait_for_ready: bool
    ) -> _SignalBinding:
        binding_path = signal_dir / self.BINDING_FILE
        busy_path = signal_dir / self.BUSY_FILE
        identity_path = signal_dir / self.IDENTITY_FILE

        while busy_path.exists():
            busy_binding = self._read_busy_binding(busy_path)
            if busy_binding is None:
                continue

            cached_identity = self._read_cached_identity(identity_path)
            if cached_identity is None or not self._same_generation(busy_binding, cached_identity):
                await self._require_target_shell_idle()
                busy_path.unlink(missing_ok=True)
                break

            validated_busy_binding = await self._validated_target_binding(cached_identity)

            if validated_busy_binding is None:
                busy_path.unlink(missing_ok=True)
                break

            if not wait_for_ready:
                if validated_busy_binding.handler_digest != handler_digest:
                    raise SignalShellBusyError(
                        "The target zsh is busy; installing the updated signal handler was deferred."
                    )

                self._write_identity(identity_path, validated_busy_binding)
                return validated_busy_binding

            await self._wait_until_not_busy(signal_dir, validated_busy_binding.pid)

        binding = self._read_cached_binding(binding_path, identity_path, handler_digest)

        if binding is not None:
            validated = await self._validated_target_binding(binding)
            if validated is not None:
                return validated

        await self._require_target_shell_idle()
        self._invalidate_binding(signal_dir)

        binding = await self._install(signal_dir, handler_digest)
        validated = await self._validated_target_binding(binding)

        if validated is None:
            self._invalidate_binding(signal_dir)
            raise RuntimeError("The installed signal handler does not belong to the target iTerm2 session.")

        # The shell publishes live trap readiness. Python records the process
        # identity it independently observed. A cached binding is reusable only
        # while both records continue to agree.
        self._write_identity(identity_path, validated)
        return validated

    async def _require_target_shell_idle(self) -> None:
        shell_value = await self.__state.get_session_var("shell")
        job_value = await self.__state.get_session_var("jobName")
        shell_name = self._shell_name(str(shell_value)) if shell_value else ""
        job_name = self._shell_name(str(job_value)) if job_value else ""

        if shell_name != self.__shell:
            raise RuntimeError(
                f"The selected session shell changed from {self.__shell!r} to {shell_name or 'unknown'!r}."
            )

        if job_name != shell_name:
            raise SignalShellBusyError(
                "The target zsh is not the foreground job; signal-handler installation was deferred "
                f"instead of sending shell input to {job_name or 'an unknown job'!r}."
            )

    async def _install(self, signal_dir: Path, handler_digest: str) -> _SignalBinding:
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
            # Zsh. The install file is the actual protocol boundary.
            await self.__state._send_text(command, suppress=True)

            payload = await self._wait_for_file(ack_path, self.INSTALL_TIMEOUT)
            return self._parse_install_ack(payload, install_nonce, handler_digest)
        finally:
            ack_path.unlink(missing_ok=True)

    async def _validated_target_binding(self, binding: _SignalBinding) -> _SignalBinding | None:
        try:
            self._assert_process_alive(binding.pid)
            target_tty = self._normalize_tty(str(await self.__state.get_session_var("tty")))
            process_tty, process_start, process_name = await asyncio.to_thread(self._read_process_identity, binding.pid)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
            return None

        # The PID must still be a Zsh on the exact TTY owned by the selected
        # iTerm2 session. This prevents stale PID reuse across sessions.
        if target_tty != process_tty or self._shell_name(process_name) != "zsh":
            return None

        if binding.tty and self._normalize_tty(binding.tty) != process_tty:
            return None

        if binding.process_start and self._normalize_whitespace(binding.process_start) != process_start:
            return None

        return replace(binding, tty=process_tty, process_start=process_start)

    @classmethod
    def _read_cached_binding(
        cls, binding_path: Path, identity_path: Path, handler_digest: str
    ) -> _SignalBinding | None:
        if binding_path.is_symlink():
            return None

        try:
            binding_fields = binding_path.read_text(encoding="utf-8").rstrip("\n").split("\t")
        except (FileNotFoundError, OSError):
            return None

        try:
            if len(binding_fields) != 6:
                return None

            version, status, pid_text, signal_name, received_digest, generation = binding_fields
            if version != cls.PROTOCOL_VERSION or status != "ready" or received_digest != handler_digest:
                return None

            binding = cls._binding_from_fields(
                pid_text=pid_text,
                signal_name=signal_name,
                handler_digest=received_digest,
                generation=generation,
                tty="",
                process_start="",
            )
            identity = cls._read_cached_identity(identity_path)
            return identity if identity is not None and cls._same_generation(binding, identity) else None
        except RuntimeError:
            return None

    @classmethod
    def _read_cached_identity(cls, identity_path: Path) -> _SignalBinding | None:
        if identity_path.is_symlink():
            return None

        try:
            fields = identity_path.read_text(encoding="utf-8").rstrip("\n").split("\t")
        except (FileNotFoundError, OSError):
            return None

        if len(fields) != 8:
            return None

        version, status, pid_text, signal_name, handler_digest, generation, tty, process_start = fields
        if version != cls.PROTOCOL_VERSION or status != "cached":
            return None

        try:
            return cls._binding_from_fields(
                pid_text=pid_text,
                signal_name=signal_name,
                handler_digest=handler_digest,
                generation=generation,
                tty=tty,
                process_start=process_start,
            )
        except RuntimeError:
            return None

    @staticmethod
    def _same_generation(left: _SignalBinding, right: _SignalBinding) -> bool:
        return (
            left.pid == right.pid
            and left.signal_number == right.signal_number
            and left.handler_digest == right.handler_digest
            and left.generation == right.generation
        )

    @classmethod
    def _read_busy_binding(cls, busy_path: Path) -> _SignalBinding | None:
        if busy_path.is_symlink():
            raise RuntimeError(f"Refusing to use symlinked signal marker: {busy_path}")

        try:
            fields = busy_path.read_text(encoding="utf-8").rstrip("\n").split("\t")
        except FileNotFoundError:
            return None
        except OSError as error:
            raise RuntimeError(f"Unable to read signal busy marker: {busy_path}") from error

        if len(fields) != 6:
            raise RuntimeError("Malformed signal busy marker.")

        version, status, pid_text, signal_name, handler_digest, generation = fields
        if version != cls.PROTOCOL_VERSION or status != "busy":
            raise RuntimeError("Unsupported signal busy marker.")

        return cls._binding_from_fields(
            pid_text=pid_text,
            signal_name=signal_name,
            handler_digest=handler_digest,
            generation=generation,
            tty="",
            process_start="",
        )

    @classmethod
    def _parse_install_ack(cls, payload: bytes, nonce: str, handler_digest: str) -> _SignalBinding:
        fields = payload.decode("utf-8").rstrip("\n").split("\t", 6)

        if len(fields) < 6:
            raise RuntimeError("Malformed signal-install acknowledgment.")

        version, status, pid_text, signal_name, received_nonce, received_digest = fields[:6]

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
        cls, *, pid_text: str, signal_name: str, handler_digest: str, generation: str, tty: str, process_start: str
    ) -> _SignalBinding:
        try:
            pid = int(pid_text)
            signal_number = signal.Signals(getattr(signal, f"SIG{signal_name}"))
        except (AttributeError, KeyError, ValueError) as error:
            raise RuntimeError("Malformed PID or signal in shell binding.") from error

        if (
            pid <= 0
            or signal_name not in {"USR1", "USR2"}
            or not cls._is_hex(handler_digest, length=64)
            or not cls._is_hex(generation, length=32)
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
    def _is_hex(value: str, *, length: int) -> bool:
        if len(value) != length:
            return False

        try:
            bytes.fromhex(value)
        except ValueError:
            return False

        return True

    @classmethod
    def _write_identity(cls, path: Path, binding: _SignalBinding) -> None:
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
        cls._atomic_write(path, payload.encode("utf-8") + b"\n")

    @classmethod
    def _invalidate_binding(cls, signal_dir: Path) -> None:
        (signal_dir / cls.BINDING_FILE).unlink(missing_ok=True)
        (signal_dir / cls.IDENTITY_FILE).unlink(missing_ok=True)

    @classmethod
    def _cleanup_request_artifacts(cls, signal_dir: Path) -> None:
        for prefix in cls.REQUEST_ARTIFACT_PREFIXES:
            for path in signal_dir.glob(f"{prefix}.*"):
                path.unlink(missing_ok=True)

    @classmethod
    @asynccontextmanager
    async def _installation_lock(cls, signal_dir: Path) -> AsyncGenerator[None, None]:
        async with cls._file_lock(signal_dir / cls.INSTALL_LOCK_FILE, cls.INSTALL_LOCK_TIMEOUT):
            yield

    @classmethod
    @asynccontextmanager
    async def _operation_lock(cls, signal_dir: Path) -> AsyncGenerator[None, None]:
        async with cls._file_lock(signal_dir / cls.OPERATION_LOCK_FILE, None):
            yield

    @classmethod
    @asynccontextmanager
    async def _file_lock(cls, lock_path: Path, timeout: float | None) -> AsyncGenerator[None, None]:
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        acquired = False

        try:
            os.fchmod(descriptor, 0o600)
            loop = asyncio.get_running_loop()
            deadline = None if timeout is None else loop.time() + timeout

            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if deadline is not None and loop.time() >= deadline:
                        raise TimeoutError(f"Timed out waiting for the signal lock: {lock_path}") from None
                    await asyncio.sleep(cls.POLL_INTERVAL)

            yield
        finally:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @classmethod
    def _handler_digest(cls) -> str:
        if not cls.SIGNAL_SCRIPT.is_file():
            raise FileNotFoundError(f"Packaged signal handler not found: {cls.SIGNAL_SCRIPT}")
        return hashlib.sha256(cls.SIGNAL_SCRIPT.read_bytes()).hexdigest()

    @staticmethod
    def _read_process_identity(pid: int) -> tuple[str, str, str]:
        def ps_field(field: str) -> str:
            completed = subprocess.run(
                ["/bin/ps", "-p", str(pid), "-o", f"{field}="], check=True, capture_output=True, text=True
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
    def _shell_name(shell: ShellType) -> str:
        return Path(str(shell)).name.lstrip("-")

    def _require_supported_shell(self) -> None:
        if not self.supports(self.__shell):
            raise RuntimeError(f"Signal command execution requires zsh; got {self.__shell!r}.")

    @staticmethod
    def _normalize_tty(value: str) -> str:
        return value.strip().removeprefix("/dev/")

    @staticmethod
    def _normalize_whitespace(value: str) -> str:
        return " ".join(value.split())

    @classmethod
    def _prepare_signal_dir(cls, session_id: str) -> Path:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        session_dir = cls.SIGNAL_ROOT / digest

        for directory in (cls.SIGNAL_ROOT, session_dir):
            if directory.is_symlink():
                raise RuntimeError(f"Refusing to use symlinked signal directory: {directory}")

            directory.mkdir(parents=True, exist_ok=True, mode=0o700)

            if not directory.is_dir():
                raise NotADirectoryError(directory)

            directory.chmod(0o700)

        return session_dir

    @classmethod
    async def _wait_for_file(cls, path: Path, timeout: float | None, *, process_pid: int | None = None) -> bytes:
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout

        while True:
            try:
                return path.read_bytes()
            except FileNotFoundError:
                if process_pid is not None:
                    cls._assert_process_alive(process_pid)

                if deadline is not None and loop.time() >= deadline:
                    raise TimeoutError(f"Timed out waiting for shell acknowledgment: {path.name}") from None

                await asyncio.sleep(cls.POLL_INTERVAL)

    @classmethod
    async def _wait_until_not_busy(cls, signal_dir: Path, process_pid: int) -> None:
        busy_path = signal_dir / cls.BUSY_FILE

        while True:
            if busy_path.is_symlink():
                raise RuntimeError(f"Refusing to use symlinked signal marker: {busy_path}")

            if not busy_path.exists():
                return

            cls._assert_process_alive(process_pid)
            await asyncio.sleep(cls.POLL_INTERVAL)

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(temporary, flags, 0o600)

        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _validate_started(cls, payload: bytes, pid: int, nonce: str) -> None:
        fields = payload.decode("utf-8").rstrip("\n").split("\t")
        if fields != [cls.PROTOCOL_VERSION, "started", str(pid), nonce]:
            raise RuntimeError("Malformed signal-start acknowledgment.")

    @classmethod
    def _parse_response(cls, payload: bytes, pid: int, nonce: str) -> tuple[int, int, int]:
        fields = payload.decode("utf-8").rstrip("\n").split("\t")

        if len(fields) != 7:
            raise RuntimeError("Malformed signal response acknowledgment.")

        version, status, pid_text, received_nonce, command_status, prompt_status, redraw_status = fields

        if version != cls.PROTOCOL_VERSION or status != "ok":
            raise RuntimeError("Shell returned an unsupported signal response.")

        if pid_text != str(pid) or received_nonce != nonce:
            raise RuntimeError("Signal response identity mismatch.")

        try:
            return int(command_status), int(prompt_status), int(redraw_status)
        except ValueError as error:
            raise RuntimeError("Signal response contains a malformed status.") from error

    @staticmethod
    def _raise_refresh_errors(prompt_status: int, redraw_status: int) -> None:
        if prompt_status != 0:
            raise RuntimeError(f"A precmd hook failed while refreshing the prompt (status={prompt_status}).")

        if redraw_status != 0:
            raise RuntimeError(f"ZLE failed to redraw the prompt (status={redraw_status}).")

    @staticmethod
    def _assert_process_alive(pid: int) -> None:
        try:
            # Signal 0 checks existence and permission without delivering a real signal.
            os.kill(pid, 0)
        except (PermissionError, ProcessLookupError) as error:
            raise RuntimeError(f"The acknowledged zsh process {pid} is no longer available.") from error
