# Environment Tool Generation

## Codex Desktop Local Environment Generation Flow

1. `.codex/environments/environment.toml`
2. setup script runs `uv sync --dev --python=3.x`
3. creates `.codex/bin/python` and `.codex/bin/python3` symlinks
4. writes `.codex/env.sh`
5. Install Project Executables action sources `.codex/env.sh`
6. `>>> uv tool install --force --editable . --project=. --python=./.venv/bin/python`
7. `UV_TOOL_DIR` sends tool venv/state to `.codex/tools`
8. `UV_TOOL_BIN_DIR` sends command shims to `.codex/bin`
9. `.codex/bin/<tool_executable_name>` and `.codex/bin/<package-name>` symlink into `<package-name>/.codex/tools/iterm2-api-wrapper/bin/`

## Instructions

1. Create [\<package-name\>/.codex/env.sh](./env.sh)

    ```shell
    export PACKAGE="$(basename $PWD)"
    export COMMAND="$(basename $PWD | tr '-' '_')"
    export PYTHON_PATH="$(pwd)/.venv/bin/python"
    export PYTHON_VERSION="$("$PYTHON_PATH" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

    export PATH="$PWD/.codex/bin:$PWD/.venv/bin:$PATH"
    export UV_CACHE_DIR="/private/tmp/$PACKAGE-uv-cache"
    export UV_SYSTEM_CERTS="true"
    unset SSL_CERT_FILE
    export UV_TOOL_DIR="$PWD/.codex/tools"
    export UV_TOOL_BIN_DIR="$PWD/.codex/bin"

    # ... any other variables ....
    ```

2. Run the following commands from the repository root

    ```shell
    source .codex/env.sh
    uv tool install --force --editable . --project=. --python=./.venv/bin/python
    ```

## Notes

- Live iTerm integration tests must be run outside the normal Codex sandbox. The sandboxed process may not see the already-running `iTerm2` app via `PyObjC`/`NSRunningApplication`, causing the wrapper to attempt a fresh launch and macOS to report a misleading "iTerm.app is corrupt / executable missing" error. Use:

    ```shell
    IT2_PYTEST_INTEGRATION=1 pytest tests/test_client_integration.py
    ```

    with escalated/unsandboxed execution.
