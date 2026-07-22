"""Handles the execution of running commands in the background without visually disturbing the iTerm2 session."""

import os
import signal
import subprocess
from pathlib import Path

from ..state import iTermState


class Background(subprocess.Popen):
    def __init__(self, state: iTermState, args: subprocess._CMD) -> None:
        super().__init__(args)
        self.__state = state

    async def cd(self, path: str) -> None:
        shell_pid = await self.fetch_zsh_pid()
        signal_dir = Path.home() / ".iterm2/api-wrapper/signals"

        signal_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        signal_dir.chmod(0o700)
        (signal_dir / f".iterm2_cd_target.{shell_pid}").write_text(path)
        os.kill(shell_pid, signal.SIGUSR1)

    async def fetch_zsh_pid(self) -> int:
        root_pid = int(await self.__state.get_session_var("effective_root_pid"))
        # print(f"{root_pid=}")
        out = self.communicate()
        out = subprocess.run(
            ["pgrep", "-P", str(root_pid)],
            capture_output=True,
            text=True,
        ).stdout.split()
        # print(f"{out=}")
        for pid in out:
            cmd = subprocess.run(
                ["ps", "-p", pid, "-o", "comm="],
                capture_output=True,
                text=True,
            ).stdout.strip()
            # print(f"[ps -p {pid} -o comm=] --> {cmd}")
            if cmd.endswith("zsh"):
                return int(pid)
        raise RuntimeError(f"no zsh child under login pid {root_pid}")
