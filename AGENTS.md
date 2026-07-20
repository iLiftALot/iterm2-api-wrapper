# Agent Instructions

## Operating Rules

- Do not modify code unless the user explicitly asks. For audits, report the issue and provide exact drop-in snippets.
- When edits are authorized, keep changes narrow, design-aligned, and verified with direct `uv run --python=3.10 ...` commands unless intentionally checking another supported Python version.
- When the user asks for code snippets, provide exact drop-in code, show the code being replaced, and explain the contract the change preserves. Use the `context7` tool for current documentation before generating code against non-standard-library APIs.
- If an authorized implementation leaves material behavior ambiguous, ask specific questions that explain the affected code location, the available choices, and why the decision matters before editing.
- Root `AGENTS.md` and its `CLAUDE.md` companion symlink are tracked; ordinary `git status` and `git diff` show changes to them.
- If sandboxing blocks `~/.cache/uv`, prefix uv commands with `UV_CACHE_DIR=/private/tmp/iterm2-api-wrapper-uv-cache`.
- Codex Desktop setup is defined by tracked `.codex/environments/environment.toml`, which generates ignored `.codex/env.sh`; generated `.codex/bin/` and `.codex/tools/` are also ignored. The generated environment and default test action set `IT2_PYTEST_INTEGRATION=0`, while the explicit integration-test action overrides it to `1`.
- `scripts/push-ready` is the repository's pre-push workflow. When installed as the hook it can format `src/` and `tests/`, amend `HEAD` using already-staged changes, run Ruff and the offline test suite, and perform an inner push. It never stages files itself. Do not invoke it during a read-only audit or when commit mutation is not explicitly intended.
- Do not preserve stale tests by reintroducing old code paths. Update tests to the intended design when the user clarifies that legacy behavior is unwanted.
- Do not add compatibility/legacy layers unless the user explicitly asks for backwards compatibility; this package favors clean, current behavior over carrying removed APIs.

## Project Snapshot

- Python package `iterm2-api-wrapper` in `src/iterm2_api_wrapper`; it requires Python `>=3.10`, tracks Python 3.10-3.15 classifiers, and uses `uv_build`.
- Runtime target is macOS + iTerm2 with the iTerm2 Python API enabled.
- AppleScript hotkey-window support needs the optional `applescript` extra; docs claiming `py-applescript` installs automatically are stale.
- Console scripts are `iterm2_api_wrapper` and `iterm`; the `it2w` alias in `docs/usage.rst` is stale.
- Public imports currently expose `CommandExecutionStatus`, `CommandExitCode`, `PrettyLog`, `close_all_shared_clients`, `close_shared_client`, `create_iterm_client`, `create_iterm_state`, `get_default_log_config`, `get_shared_client`, `iTermAPI`, `iTermClient`, `iTermConnection`, `iTermState`, and `logger` (the old `CommandStatus` is gone; use `CommandExecutionStatus`).
- Runtime construction flows through `client.py` -> `gateway.py` -> `api/it2runtime.py` / `api/it2api.py`; `state.py` owns resolved-session behavior, while `api/it2profile.py` owns profile schemas, local profile updates, and wrapper-managed dynamic-profile persistence. Avoid rebuilding these owners elsewhere.

## Commands

| Task | Command |
| --- | --- |
| Sync dev env | `uv sync --group dev --group ci` |
| Lint | `uv run --python=3.10 --group dev --group ci ruff check .` |
| Format check | `uv run --python=3.10 --group dev --group ci ruff format --check .` |
| Unit tests | `IT2_PYTEST_INTEGRATION=0 uv run --python=3.10 --group dev pytest` |
| Focused unit subset | `IT2_PYTEST_INTEGRATION=0 uv run --python=3.10 --group dev pytest tests/test_gateway.py tests/test_client.py` |
| Integration tests | `IT2_PYTEST_INTEGRATION=1 uv run --python=3.10 --group dev pytest tests/test_client_integration.py` |
| Typecheck | `uv run --python=3.10 --group dev --group ci pyright ./src ./tests` |
| Build docs | `uv run --python=3.10 --group dev sphinx-build -b html docs docs/_build` |

## Command Drift

- `just format`, `just lint`, and the ordinary test recipes use `uv run --active --python=3.10 --group dev`; formatting/linting also add `--group ci`. `just typecheck` deliberately omits `--active`, while docs/IPython/build recipes use different invocations. `test-pyversions` covers Python 3.10-3.15. `pyproject.toml` has no optional `test` extra, so do not add `--extra test` to project commands.
- Avoid mutating `just lint`, `just format`, `just qa`, `just build`, and clean recipes unless the user asks: they run Ruff fixes/formatting, remove artifacts, or reinstall tool executables. Prefer the non-mutating direct commands above for audits.
- Typechecking uses `pyright`, declared in the `ci` dependency group (`ci = ["ruff", "pyright"]`) and run as `pyright ./src ./tests` by `just typecheck` and `.github/workflows/validate.yml`; the older `ty` executable is no longer used.
- A docs build currently exits 0 with warnings for the missing `iterm2_api_wrapper.setup` module and the short title underline in `docs/index.rst`; network-restricted runs also warn when the Python intersphinx inventory cannot be fetched. `iterm2_api_wrapper.utils` now imports successfully. Treat source `.rst` files as more authoritative than generated `docs/_build/`.

## Design Preferences

- Prefer simple, explicit object responsibilities over compatibility shims. Lookup methods should return the best matching object without replacing `self.window`, `self.tab`, `self.session`, or the active `self.profile`; cache population is allowed. Active-context assignment belongs to `_initialize()` or another explicitly named setup/selection operation. `get_session()` currently has a setup-time profile-configuration exception; do not expand or copy that exception into other getters.
- Keep `iTermState` focused on stateful iTerm session orchestration. `LoopManager` owns event-loop reconciliation, `MarkedCommand` owns synthetic OSC 133 command wrappers, and `Parser` owns coordinate-range extraction, prompt cleanup, and snapshot-diff fallback. Do not move those implementations back into `state.py`.
- Live iTerm2 shell integration and `PromptMonitor` events are the primary completion path. When live integration is unavailable, `run_command()` intentionally uses `MarkedCommand` to execute a temporary Zsh script that emits synthetic OSC 133 marks, with `Parser` retaining snapshot-diff recovery for incomplete or mismatched prompt data. Keep the live probe, synthetic-mark wrapper, and parser fallback as separate owners.
- Command timeout semantics are intentionally loose/inactivity-based. A timeout is a "no progress/no events for this long" guard, not a hard wall-clock budget for the whole command, because agents often cannot estimate command duration accurately.
- Long-running commands that are known active, still updating terminal contents, or have not returned to the prompt should not fail solely because the initial timeout estimate was too short.
- For prompt-monitor execution, subscribe before sending command text. Do not schedule `async_send_text` before the `PromptMonitor` is active, and do not wait for prompt notifications inside an iTerm transaction.
- Never dump full terminal snapshots to logs during command execution; this changes the terminal buffer being observed and makes debugging output self-interfering.

## Profile Typing And Dynamic-Profile Contracts

- `src/iterm2_api_wrapper/api/it2profile.py` models iTerm2's raw plist property dictionaries with exact human-readable keys. Because many keys contain spaces and punctuation, retain functional `TypedDict` declarations; nested structures such as colors, keyboard maps, smart-selection rules, triggers, title functions, and status-bar layouts carry their own value shapes. Use `BoolInt = Literal[0, 1]` where iTerm2 serializes booleans as plist integers, and reserve `Any` for upstream structures whose shape is not yet known.
- Top-level profile mappings are intentionally partial. `ProfilePropertiesNoIdentifiers` contains every known ordinary property except `Name` and `Guid`, all optional; `_OptionalProfileIdentity` adds optional identity; and `ProfileProperties` combines them for patches, partial RPC results, session-local updates, and `all_properties`. Do not make ordinary profile properties globally required merely because a complete persisted dynamic profile needs identity.
- `ProfilePropertyKey` must stay synchronized with every key in `ProfileProperties`; `tests/test_profile.py::test_profile_property_key_covers_every_profile_property` enforces exact equality. `ProfilePropertyLike.key` and `ProfileProperty.key` intentionally use `ProfilePropertyKey | str`: the literal members provide editor autocomplete for known iTerm2 keys, while `str` deliberately permits custom, newly introduced, or otherwise unmodeled upstream keys. Do not simplify this annotation to plain `str` or narrow it to literal-only.
- `ProfilePropertyLike` is the structural boundary for protobuf-style RPC properties (`key` plus JSON-encoded `json_value`). `ProfileProperty` is the wrapper-owned implementation and JSON-encodes values by default; `Profile.__init__` accepts either a typed mapping or a sequence of wire-property objects and normalizes both through the upstream profile constructor. The wrapper annotates upstream `_Profile__props`, returns a defensive typed copy from `all_properties`, and keeps `guid` truthfully typed as `str` by raising `BadGUIDException` when RPC data omits it or provides a malformed value.
- Keep persisted and runtime dynamic-profile fields separate. `_DynamicProfileDefinitionExtras` contains JSON-writable parent selectors and `Rewritable`; `_DynamicProfileRuntimeExtras` contains iTerm2-produced `Dynamic Profile Filename` and `Is Dynamic Profile`, which must never be written to a `DynamicProfiles` JSON file. `DynamicProfileProperties` is a fully optional partial persisted mapping, while `DynamicProfileRuntimeProperties` extends it only for RPC/runtime reads.
- `DynamicProfileDefinition` is the completed persistence contract: it inherits optional non-identity properties and optional definition extras, then requires exactly `Name: str` and `Guid: str`. `DynamicProfilesPayload` requires `Profiles: list[DynamicProfileDefinition]`. Preserve this split instead of redefining optional `Name`/`Guid` from `ProfileProperties` as required in a subclass; separate identity ownership accurately represents the partial and finished usage contexts and avoids invalid `TypedDict` requiredness redefinition.
- Dynamic-profile create/update value patches accept `ProfilePropertiesNoIdentifiers`, so callers cannot overwrite deterministic identity through `properties`. Constructor overloads permit a parent GUID, a parent name, or neither, but never both; the runtime check mirrors that static contract. The constructor copies caller data into `__requested_properties`, builds a separate complete `DynamicProfileDefinition`, derives a repeatable uppercase UUID5 GUID from user plus normalized profile name, forces `Rewritable=True`, and records exactly one parent selector.
- `_load_dynamic_profiles_payload` treats JSON as an untrusted boundary: require a document object, a `Profiles` list, object entries, and string `Name`/`Guid` before casting to `DynamicProfilesPayload`. It intentionally validates the envelope and universally required identity, not all hundreds of optional property value types. `DynamicProfile.payload` prepends the current definition, preserves other validated definitions, and replaces any prior entry with the same deterministic GUID.
- Dynamic-profile persistence stages the complete JSON outside iTerm2's watched `DynamicProfiles` directory and atomically replaces `iterm2-api-wrapper.json`; `_wait_for_profile` polls `Profile.async_get` with capped exponential backoff until iTerm2 exposes a typed `Profile` or the load timeout expires. `async_create` delegates to update when the deterministic GUID already resolves to a runtime profile marked `Is Dynamic Profile`.
- `Profile.async_local_update` is session-scoped and uses `LocalWriteOnlyProfile`; it must not be conflated with persisted dynamic-profile updates. The static `Profile.async_update` delegates to `DynamicProfile.async_update`, whose intended patch contract preserves unspecified fields, removes explicit fields so they inherit from the parent, and rejects protected identity/parent/runtime fields and set/remove conflicts.
- Current limitation: `DynamicProfile.async_update` and `_wait_for_profile_update` still raise `NotImplementedError`. Consequently, `async_create` also raises for an already registered dynamic profile because it delegates to the unfinished update path. Do not describe dynamic-profile updating as implemented or make the existing-profile test expect success until both methods land.

## Source Map

- `src/iterm2_api_wrapper/client.py`: `iTermClient`, background event loop, gateway injection, state refresh, shared client registry (`get_shared_client`, `close_shared_client`, `close_all_shared_clients`).
- `src/iterm2_api_wrapper/gateway.py`: `ITermGateway`/`DefaultITermGateway` protocol boundary; lazily imports iTerm2 and `pyobjc_adapter` inside methods so importing the package stays test-friendly off macOS; owns `IT2_CONNECT_TIMEOUT`.
- `src/iterm2_api_wrapper/pyobjc_adapter/`: AppKit/PyObjC runtime boundary (`PyObjcContainer`, `async_ensure_iterm_app_running`, `is_iterm_app_running`) launching/activating iTerm2 via `NSRunningApplication`; `pyobjc_typings.pyi` holds the typed AppKit shims (the sibling `pyobjc_typings.py` only re-exports the untyped PyObjC symbols at runtime).
- `src/iterm2_api_wrapper/api/it2api.py`: `iTermAPI`, iTerm2 activation/setup, profile lookup, dedicated tagged window/tab/session selection.
- `src/iterm2_api_wrapper/api/it2app.py`: typed `App` singleton construction, typed window/tab/session lookup methods, and a re-entrancy guard preventing upstream focus-refresh recursion.
- `src/iterm2_api_wrapper/api/it2profile.py`: exact-key typed views of iTerm2's plist-backed profile dictionaries; typed `Profile`, `PartialProfile`, and `LocalWriteOnlyProfile` wrappers; session-local profile mutation; deterministic wrapper-managed dynamic-profile definition, validation, persistence, and registration polling. Dynamic-profile update contracts exist, but `DynamicProfile.async_update()` and `_wait_for_profile_update()` currently raise `NotImplementedError`.
- `src/iterm2_api_wrapper/api/it2session.py`: typed `Session` wrapper; directly performs the profile-property RPC and constructs a session-backed `Profile`, preserving the session ID required by local profile updates.
- `src/iterm2_api_wrapper/api/it2*.py`: typed wrappers around upstream iTerm2 alert/app/connection/lifecycle/measurement/prompt/tab/transaction/variable/window APIs (`it2transaction.py` exposes `Transaction`; `it2alert.py` exposes `Alert`, `TextInputAlert`, `PolyModalAlert`).
- `src/iterm2_api_wrapper/state.py`: `iTermState`, active-context validation and refresh, variable access, escape sending, command orchestration, shell-integration probing, and prompt-monitor lifecycle. It delegates loop reconciliation, synthetic command marks, and terminal parsing/fallback cleanup to `utils/`.
- `src/iterm2_api_wrapper/api/it2connection.py`: custom `Connection` wrapper for current `websockets` behavior and run helpers.
- `src/iterm2_api_wrapper/typings.py`: shared `TypedDict` setup/state kwargs, including `profile_properties: ProfileProperties`; `HexCodeEnum` and literal-name autocomplete types; `CommandExitCode`, `CommandExecutionStatus`, and `CommandExecutionResult`.
- `src/iterm2_api_wrapper/utils/`: shared utilities; `parser.py` owns `Parser`/`ParseResult` coordinate-range reads, prompt/command/output extraction, soft-wrap joining, and snapshot-diff fallback; `loop_manager.py` reconciles state and connection loops; `marked_command.py` owns context-managed temporary Zsh scripts with per-command `aid`-qualified OSC 133 marks; package `__init__.py` exports `Parser`.
- `src/iterm2_api_wrapper/zsh/iterm_shell_integration.zsh`: local `aid`-aware Zsh shell-integration asset under development; it is currently unreferenced by Python runtime code and lacks an explicit package-data rule, so do not describe it as installed or automatically sourced.
- `src/iterm2_api_wrapper/errors.py`: `iTermError` base (via `ErrorMeta`) plus `ProfileNotFoundError`, `WindowNotFoundError`, `TabNotFoundError`, `SessionNotFoundError`.
- `src/iterm2_api_wrapper/cli.py`: Typer dispatcher taking `func_name` plus positional/`key=value` arguments; owns function-name, function-argument, variable-scope/value, profile, and `HexCodeEnum` shell completions.
- `src/iterm2_api_wrapper/alert.py`: async alert command handlers (`alert_handler` and friends) built atop `api/it2alert.py`.
- `src/iterm2_api_wrapper/main.py`: programmatic entry point exposing `create_iterm_state`, `init`, and `run_until_complete`.
- `src/iterm2_api_wrapper/_logging/`: custom Rich-backed `PrettyLog` stack used by package and tests.
- `src/iterm2_api_wrapper/mac/`: AppleScript hotkey-window helpers (`platform_macos.py` `maybe_reveal_hotkey_window`, gated on the optional `applescript` extra) plus tracked `applescripts/` source (`.applescript`) and compiled (`.scpt`) files.

## Tests And Runtime

- With `IT2_PYTEST_INTEGRATION=0`, the default suite skips the live client integration tests and covers alert, API, app, CLI, client, connection, errors, gateway, logging, macOS helpers, measurement, package entry points, parser, profile, prompt, runtime setup, state, and shared typings.
- `tests/test_gateway.py`, `tests/test_gateway_defaults.py`, and `tests/test_client.py` use fakes and do not require live iTerm2.
- `tests/test_client_integration.py` is opt-in via `IT2_PYTEST_INTEGRATION=1` and requires iTerm2 running with Python API enabled.
- Test logging writes `logs/pytest.log`, `logs/pytest.html`, and pytest's `trace` debug file; all are ignored artifacts.
- Importing the top-level package loads `.env` and initializes the package's lazy `PrettyLog` registry. Import alone does not open or mutate `logs/iterm2_api_wrapper.log`; the file is opened on the first file-output operation.
- Runtime/test knobs include `IT2_CONNECT_TIMEOUT`, `IT2_DEFAULT_PROFILE`, `IT2_DEBUG`, `IT2_INTEGRATION_TIMEOUT`, `IT2_INTEGRATION_LOG`, `IT2_NEW_APP_TIMEOUT`, `IT2_PYTEST_INTEGRATION`, `IT2_APP_PATH`, `IT2_SUITE`, `IT2_BUNDLE_ID`, and the legacy misspelled `IT2_APP_PATH`; conftest also reads HTML-report theming knobs `IT2_PROFILE`, `IT2_PROFILE_ID`, `PYTEST_THEME_PATH`, `PYTEST_HTML_THEME_PROFILE`, `PYTEST_HTML_THEME_PROFILE_ID`, `PYTEST_HTML_THEME_CSS_PATH`, and `PYTEST_HTML_THEME_CSS`.
- Live command smoke tests can be run from VS Code's terminal while targeting iTerm2; do not assume the caller's terminal is the target iTerm session.
- When command behavior changes, validate both a fast command such as `echo final-smoke` and a loose-timeout command such as `sleep 3 && echo HEY && sleep 3 && echo BYE` with `timeout=5.0`.
- `tests/test_profile.py` covers wrapper construction, partial queries, required dynamic-profile payload fields, exclusion of runtime-only keys, parent-selector validation, registration polling, and exact parity between `ProfilePropertyKey` and `ProfileProperties`. Dynamic-profile update behavior remains incomplete; the existing-profile create case currently reaches `NotImplementedError` through `async_update`.

## Docs And Artifacts

- Prefer `pyproject.toml`, `justfile`, `.github/workflows/validate.yml`, and source files over stale cookiecutter text in `CONTRIBUTING.md`.
- `docs/api/setup.rst` still references the absent `iterm2_api_wrapper.setup` module. `docs/api/utils.rst` now resolves the real `iterm2_api_wrapper.utils` package successfully through its tracked `__init__.py`.
- Generated/local artifacts include `build/`, `dist/`, `docs/_build/`, `logs/`, `trace`, `htmlcov/`, `.coverage`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, Python bytecode/cache directories, `.venv/`, `.agent-workspace/`, `.agents/`, `.super-agents/`, `.claude/`, generated `.codex/env.sh`, `.codex/bin/`, `.codex/tools/`, `assets/*`, egg metadata, wheels, and tarballs.
