# Agent Instructions

## Operating Rules

- Do not modify code unless the user explicitly asks. For audits, report the issue and provide exact drop-in snippets.
- When edits are authorized, keep changes narrow, design-aligned, and verified with direct `uv run --python=3.10 ...` commands unless intentionally checking another supported Python version.
- `AGENTS.md` is ignored by `.gitignore`; inspect it directly because normal `git status` / `git diff` will not show it.
- If sandboxing blocks `~/.cache/uv`, prefix uv commands with `UV_CACHE_DIR=/private/tmp/iterm2-api-wrapper-uv-cache`.
- Codex Desktop setup is configured by ignored `.codex/environments/environment.toml` plus tracked `.codex/env.sh`; generated `.codex/bin/` and `.codex/tools/` stay ignored, and default actions force `IT2_PYTEST_INTEGRATION=0`.
- Do not preserve stale tests by reintroducing old code paths. Update tests to the intended design when the user clarifies that legacy behavior is unwanted.
- Do not add compatibility/legacy layers unless the user explicitly asks for backwards compatibility; this package favors clean, current behavior over carrying removed APIs.

## Project Snapshot

- Python package `iterm2-api-wrapper` in `src/iterm2_api_wrapper`; it requires Python `>=3.10`, tracks Python 3.10-3.15 classifiers, and uses `uv_build`.
- Runtime target is macOS + iTerm2 with the iTerm2 Python API enabled.
- AppleScript hotkey-window support needs the optional `applescript` extra; docs claiming `py-applescript` installs automatically are stale.
- Console scripts are `iterm2_api_wrapper` and `iterm`; the `it2w` alias in `docs/usage.rst` is stale.
- Public imports currently expose `CommandExecutionStatus`, `CommandExitCode`, `PrettyLog`, `close_all_shared_clients`, `close_shared_client`, `create_iterm_client`, `create_iterm_state`, `get_default_log_config`, `get_shared_client`, `iTermAPI`, `iTermClient`, `iTermConnection`, `iTermState`, and `logger` (the old `CommandStatus` is gone; use `CommandExecutionStatus`).
- The codebase is centered on `api/it2api.py` for setup/selection, `api/it2runtime.py` for runtime bootstrap/capability validation, and `state.py` for active-session operations; avoid rebuilding removed setup logic elsewhere.

## Commands

| Task | Command |
| --- | --- |
| Sync dev env | `uv sync --group dev --group ci` |
| Lint | `uv run --python=3.10 --group dev --group ci ruff check .` |
| Format check | `uv run --python=3.10 --group dev --group ci ruff format --check .` |
| Unit tests | `IT2_PYTEST_INTEGRATION=0 uv run --python=3.10 --group dev pytest` |
| Focused unit subset | `IT2_PYTEST_INTEGRATION=0 uv run --python=3.10 --group dev pytest tests/test_gateway.py tests/test_client.py` |
| Integration tests | `IT2_PYTEST_INTEGRATION=1 uv run --python=3.10 --group dev pytest tests/test_client_integration.py` |
| Typecheck | `uv run --python=3.10 ty check .` |
| Build docs | `uv run --python=3.10 --group dev sphinx-build -b html docs docs/_build` |

## Command Drift

- Current `just` recipes default to `uv run --active --python=3.10 --group dev`, with `test-pyversions` covering 3.10-3.15; `pyproject.toml` has no optional `test` extra, so do not add `--extra test` to new commands.
- Avoid mutating `just lint`, `just format`, `just qa`, `just build`, and clean recipes unless the user asks: they run Ruff fixes/formatting, remove artifacts, or reinstall tool executables. Prefer the non-mutating direct commands above for audits.
- `ty check .` currently uses the `ty` executable on PATH rather than a declared project dependency and fails on existing diagnostics in `api/it2api.py`, API wrapper override/runtime patching files, `cli.py`, `errors.py`, `pyobjc_adapter`, `state.py`, and tests.
- Docs build exits 0 but emits warnings for missing `iterm2_api_wrapper.setup` / `iterm2_api_wrapper.utils` autodoc imports, `alert.py` docstrings, and the `docs/index.rst` title underline; network-restricted runs can also warn about the Python intersphinx inventory. Treat source `.rst` files as more authoritative than `docs/_build/`.

## Design Preferences

- Prefer simple, explicit object responsibilities over compatibility shims. If a method is named `get_window`, `get_tab`, `get_session`, or `get_profile`, it should retrieve the best matching object for the supplied arguments and should not mutate `self.window`, `self.tab`, `self.session`, `self.profile`, or other cached context as a side effect.
- Mutating the API object's active context must be an explicit setup/selection action, not a hidden effect of a getter.
- Keep `iTermState` focused on stateful iTerm session behavior. Move generic parsing, diffing, output-cleanup, or text helper logic to module-level functions or separate modules instead of adding static-method clutter.
- Shell integration is the primary supported command-completion path. Fallback logic may exist, but it must stay small, conservative, and reliability-focused; do not build a parallel shell-integration replacement unless asked.
- Command timeout semantics are intentionally loose/inactivity-based. A timeout is a "no progress/no events for this long" guard, not a hard wall-clock budget for the whole command, because agents often cannot estimate command duration accurately.
- Long-running commands that are known active, still updating terminal contents, or have not returned to the prompt should not fail solely because the initial timeout estimate was too short.
- For prompt-monitor execution, subscribe before sending command text. Do not schedule `async_send_text` before the `PromptMonitor` is active, and do not wait for prompt notifications inside an iTerm transaction.
- Never dump full terminal snapshots to logs during command execution; this changes the terminal buffer being observed and makes debugging output self-interfering.

## Source Map

- `src/iterm2_api_wrapper/client.py`: `iTermClient`, background event loop, gateway injection, state refresh, shared client registry (`get_shared_client`, `close_shared_client`, `close_all_shared_clients`).
- `src/iterm2_api_wrapper/gateway.py`: `ITermGateway`/`DefaultITermGateway` protocol boundary; lazily imports iTerm2 and `pyobjc_adapter` inside methods so importing the package stays test-friendly off macOS; owns `ITERM_CONNECT_TIMEOUT`.
- `src/iterm2_api_wrapper/pyobjc_adapter/`: AppKit/PyObjC runtime boundary (`PyObjcContainer`, `async_ensure_iterm_app_running`, `is_iterm_app_running`) launching/activating iTerm2 via `NSRunningApplication`; `pyobjc_typings.pyi` holds the typed AppKit shims (the sibling `pyobjc_typings.py` only re-exports the untyped PyObjC symbols at runtime).
- `src/iterm2_api_wrapper/api/it2api.py`: `iTermAPI`, iTerm2 activation/setup, profile lookup, dedicated tagged window/tab/session selection.
- `src/iterm2_api_wrapper/api/it2runtime.py`: iTerm2 runtime monkeypatch/bootstrap, capability validation, optional `IT2_ENHANCE_IMPORTS` import enhancement.
- `src/iterm2_api_wrapper/api/it2*.py`: typed wrappers around upstream iTerm2 alert/app/connection/lifecycle/profile/prompt/session/tab/transaction/variable/window APIs (`it2transaction.py` exposes `Transaction`; `it2alert.py` exposes `Alert`, `TextInputAlert`, `PolyModalAlert`).
- `src/iterm2_api_wrapper/state.py`: `iTermState`, variable access, escape sending, command execution, prompt/output retrieval for the current resolved state.
- `src/iterm2_api_wrapper/api/it2connection.py`: custom `Connection` wrapper for current `websockets` behavior and run helpers.
- `src/iterm2_api_wrapper/typings.py`: shared `TypedDict` setup kwargs, `HexCodeEnum`, `CommandExitCode`, `CommandExecutionStatus`, and `CommandExecutionResult`.
- `src/iterm2_api_wrapper/errors.py`: `iTermError` base (via `ErrorMeta`) plus `ProfileNotFoundError`, `WindowNotFoundError`, `TabNotFoundError`, `SessionNotFoundError`.
- `src/iterm2_api_wrapper/cli.py`: Typer dispatcher taking `func_name` plus positional/`key=value` args.
- `src/iterm2_api_wrapper/alert.py`: async alert command handlers (`alert_handler` and friends) built atop `api/it2alert.py`.
- `src/iterm2_api_wrapper/main.py`: programmatic entry point exposing `create_iterm_state`, `init`, and `run_until_complete`.
- `src/iterm2_api_wrapper/_logging/`: custom Rich-backed `PrettyLog` stack used by package and tests.
- `src/iterm2_api_wrapper/mac/`: AppleScript hotkey-window helpers (`platform_macos.py` `maybe_reveal_hotkey_window`, gated on the optional `applescript` extra) plus tracked `applescripts/` source (`.applescript`) and compiled (`.scpt`) files.

## Tests And Runtime

- The default unit suite is offline-safe with `IT2_PYTEST_INTEGRATION=0`; current coverage spans alert/api/cli/client/connection/errors/gateway/logging/mac/main/prompt/runtime/state/typings behavior.
- `tests/test_gateway.py`, `tests/test_gateway_defaults.py`, and `tests/test_client.py` use fakes and do not require live iTerm2.
- `tests/test_client_integration.py` is opt-in via `IT2_PYTEST_INTEGRATION=1` and requires iTerm2 running with Python API enabled.
- Test logging writes `logs/pytest.log`, `logs/pytest.html`, and pytest's `trace` debug file; all are ignored artifacts.
- Importing the top-level package loads `.env` and initializes package logging, so imports can create local log side effects.
- Runtime/test knobs include `ITERM_CONNECT_TIMEOUT`, `IT2_DEFAULT_PROFILE`, `ITERM_DEBUG`, `IT2_ENHANCE_IMPORTS`, `ITERM_INTEGRATION_TIMEOUT`, `ITERM_INTEGRATION_LOG`, `ITERM_NEW_APP_TIMEOUT`, `IT2_PYTEST_INTEGRATION`, `IT2_APP_PATH`, `IT2_SUITE`, `ITERM2_BUNDLE_ID`, and the legacy misspelled `IT2_EXECTUABLE_PATH`; conftest also reads HTML-report theming knobs `ITERM_PROFILE`, `IT2_PROFILE_ID`, `IT2_PYTEST_THEME_PATH`, `PYTEST_HTML_THEME_PROFILE`, `PYTEST_HTML_THEME_PROFILE_ID`, `PYTEST_HTML_THEME_CSS_PATH`, and `PYTEST_HTML_THEME_CSS`.
- Live command smoke tests can be run from VS Code's terminal while targeting iTerm2; do not assume the caller's terminal is the target iTerm session.
- When command behavior changes, validate both a fast command such as `echo final-smoke` and a loose-timeout command such as `sleep 3 && echo HEY && sleep 3 && echo BYE` with `timeout=5.0`.

## Docs And Artifacts

- Prefer `pyproject.toml`, `justfile`, `.github/workflows/validate.yml`, and source files over stale cookiecutter text in `CONTRIBUTING.md`.
- `docs/api/setup.rst` and `docs/api/utils.rst` reference modules that are not present in `src/iterm2_api_wrapper`.
- Generated/local artifacts include `docs/_build/`, `dist/`, `logs/`, `trace`, `htmlcov/`, `.coverage`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.agents/`, `.super-agents/`, `.codex/bin/`, `.codex/tools/`, `assets/*`, wheels, and tarballs.
