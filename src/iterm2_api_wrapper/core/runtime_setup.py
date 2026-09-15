from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from iterm2.capabilities import check_supports_get_default_profile, check_supports_prompt_id

from .._logging import PrettyLog
from ..api.it2prompt import check_supports_prompt_monitor_modes


if TYPE_CHECKING:
    from .gateway import Connection


log = PrettyLog.get_logger(__name__)


def _install_iterm2_connection_bridge() -> None:
    """Expose the wrapper connection implementation through upstream public APIs."""
    import iterm2
    import iterm2.connection as upstream_connection

    from ..api import it2connection as wrapper_connection

    previous_connection = upstream_connection.Connection

    # Preserve notification helpers registered before the bridge was installed.
    if previous_connection is not wrapper_connection.Connection:
        for helper in previous_connection.helpers:
            if helper not in wrapper_connection.Connection.helpers:
                wrapper_connection.Connection.helpers.append(helper)

    # Preserve callbacks registered before bridge installation and ensure that
    # old upstream callback functions still resolve the wrapper-owned registry.
    if upstream_connection.gDisconnectCallbacks is not wrapper_connection.gDisconnectCallbacks:
        for callback in upstream_connection.gDisconnectCallbacks:
            if callback not in wrapper_connection.gDisconnectCallbacks:
                wrapper_connection.gDisconnectCallbacks.append(callback)

        upstream_connection.gDisconnectCallbacks = wrapper_connection.gDisconnectCallbacks

    upstream_connection.Connection = wrapper_connection.Connection
    upstream_connection.run_until_complete = wrapper_connection.run_until_complete
    upstream_connection.run_forever = wrapper_connection.run_forever
    upstream_connection.add_disconnect_callback = wrapper_connection.add_disconnect_callback

    iterm2.Connection = wrapper_connection.Connection
    iterm2.run_until_complete = wrapper_connection.run_until_complete
    iterm2.run_forever = wrapper_connection.run_forever
    iterm2.add_disconnect_callback = wrapper_connection.add_disconnect_callback


def _enhance_imports() -> None:
    """Inject the iTerm2 package root with `__all__` for importing convenience."""
    import iterm2

    if getattr(iterm2, "__all__", None) is not None:
        return

    import json
    from pathlib import Path
    from types import ModuleType

    iterm2_exported_names: list[str] = []
    for name in dir(iterm2):
        attr = getattr(iterm2, name)
        if isinstance(attr, ModuleType) or (name.startswith("__") and name != "__version__"):
            continue

        iterm2_exported_names.append(name)

    package_root_path = Path(iterm2.__file__)
    existing_contents = package_root_path.read_text().rstrip()
    updated_contents = existing_contents + f"\n\n\n__all__ = {json.dumps(sorted(iterm2_exported_names), indent=4)}\n"
    package_root_path.write_text(updated_contents)


def _enhance_docstrings() -> None:
    import re

    import iterm2

    invalid_doc_comment_pattern = re.compile(
        r"^( {4,})"
        r"([A-Za-z]\S*[ \t]*=[ \t]*\S+)"
        r"([ \t]*#:?[ \t]+)"
        r"(?!type:[ \t]*ignore)"
        r"(.*?)$",
        flags=re.MULTILINE,
    )
    it2_source_dir = Path(iterm2.__file__).parent
    changed_files: list[tuple[Path, list[tuple[int, str, str, str]]]] = []

    for src_file in sorted(it2_source_dir.glob("*.py")):
        # Do not process backups created by an earlier invocation.
        if src_file.name.endswith(".bak.py"):
            continue

        code = src_file.read_text(encoding="utf-8")
        file_changes: list[tuple[int, str, str, str]] = []

        def replace_invalid_comment(
            match: re.Match[str], source_code: str = code, changes: list[tuple[int, str, str, str]] = file_changes
        ) -> str:
            indent, assignment, separator, description = match.groups()

            # Every prior replacement in this file adds two lines. Point the
            # clickable reference at the beginning of the rewritten block.
            original_line = source_code.count("\n", 0, match.start()) + 1
            updated_line_index = original_line + (2 * len(changes))

            commented_original = f"#{assignment}{separator}{description}"
            docstring = f'"""{description}"""'

            changes.append((updated_line_index, commented_original, assignment, docstring))

            return f"{indent}{commented_original}\n{indent}{assignment}\n{indent}{docstring}"

        updated_code = invalid_doc_comment_pattern.sub(replace_invalid_comment, code)

        if not file_changes:
            continue

        backup_path = src_file.with_name(f"{src_file.stem}.bak.py")
        backup_path.write_text(code, encoding="utf-8")
        src_file.write_text(updated_code, encoding="utf-8")
        changed_files.append((src_file, file_changes))

    for file_number, (src_file, file_changes) in enumerate(changed_files, start=1):
        try:
            display_path = src_file.relative_to(Path.cwd())
        except ValueError as e:
            log.warning(f"Could not relativize {src_file} to {Path.cwd()}: {e}")
            display_path = src_file

        # Align the hierarchy beneath the numbered root, including 10+.
        root_spacing = " " * (len(str(file_number)) + 1)

        print(f"{file_number}. \033[3m{src_file}\033[0m")

        for change_number, (line_number, commented_original, assignment, docstring) in enumerate(file_changes):
            is_last_change = change_number == len(file_changes) - 1
            change_branch = "└──" if is_last_change else "├──"
            detail_prefix = "    " if is_last_change else "│   "

            print(
                (f"{root_spacing}{change_branch} \033[4m{display_path}#{line_number}\033[0m"),
                (f"{root_spacing}{detail_prefix}├─── \033[31m- {commented_original}\033[0m"),
                (f"{root_spacing}{detail_prefix}└─── \033[32m+ {assignment}\033[0m"),
                (f"{root_spacing}{detail_prefix}     \033[32m+ {docstring}\033[0m"),
                sep="\n",
            )

        print(f"Enhanced {len(file_changes)} docstring comment(s) in {display_path!s}.")


def _check_version(connection: Connection) -> None:
    """Validate the capabilities required by iTermAPI for this connection."""
    check_supports_prompt_monitor_modes(connection)  # Protocol 1.1
    check_supports_get_default_profile(connection)  # Protocol 1.4
    check_supports_prompt_id(connection)  # Protocol 1.5

    major_version, minor_version = connection.iterm2_protocol_version
    log.debug(f"iTerm protocol version {major_version}.{minor_version}")


def validate_iterm2_runtime(connection: Connection) -> None:
    """..."""
    _enhance_imports()
    _install_iterm2_connection_bridge()
    _check_version(connection)
