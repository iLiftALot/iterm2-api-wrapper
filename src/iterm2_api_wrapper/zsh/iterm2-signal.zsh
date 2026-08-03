typeset -g _ITERM2_API_WRAPPER_SIGNAL_PROTOCOL=3

_iterm2_api_wrapper_signal_publish() {
    emulate -L zsh

    local destination=$1
    local payload=$2
    local temporary="${destination}.tmp.$$.$RANDOM"

    umask 077
    print -r -- "$payload" >| "$temporary" || return 1

    command mv -f -- "$temporary" "$destination" || {
        command rm -f -- "$temporary"
        return 1
    }
}

_iterm2_api_wrapper_signal_binding_payload() {
    emulate -L zsh

    REPLY="${_ITERM2_API_WRAPPER_SIGNAL_PROTOCOL}"$'\t'"ready"$'\t'"$$"$'\t'"${_ITERM2_API_WRAPPER_SIGNAL_NAME}"$'\t'"${_ITERM2_API_WRAPPER_SIGNAL_HANDLER_DIGEST}"$'\t'"${_ITERM2_API_WRAPPER_SIGNAL_GENERATION}"
}

_iterm2_api_wrapper_signal_busy_payload() {
    emulate -L zsh

    REPLY="${_ITERM2_API_WRAPPER_SIGNAL_PROTOCOL}"$'\t'"busy"$'\t'"$$"$'\t'"${_ITERM2_API_WRAPPER_SIGNAL_NAME}"$'\t'"${_ITERM2_API_WRAPPER_SIGNAL_HANDLER_DIGEST}"$'\t'"${_ITERM2_API_WRAPPER_SIGNAL_GENERATION}"
}

_iterm2_api_wrapper_signal_trap_is_owned() {
    emulate -L zsh

    local signal_name=$1
    local trap_dump=$2
    local line

    while IFS= read -r line; do
        if [[ $line == *"_ITERM2_API_WRAPPER_SIGNAL_HANDLER"* &&
              $line == *"--dispatch"* &&
              $line == *" ${signal_name}" ]]; then
            return 0
        fi
    done < "$trap_dump"

    return 1
}

_iterm2_api_wrapper_signal_activate() {
    emulate -L zsh

    local trap_dump

    [[ ${_ITERM2_API_WRAPPER_SIGNAL_PID-} == $$ ]] || return 0
    [[ -d ${_ITERM2_API_WRAPPER_SIGNAL_DIR-} ]] || return 0
    [[ -n ${_ITERM2_API_WRAPPER_SIGNAL_NAME-} ]] || return 0

    trap_dump="${_ITERM2_API_WRAPPER_SIGNAL_DIR}/.traps.activate.$$.$RANDOM"
    trap >| "$trap_dump" || return 1

    if ! _iterm2_api_wrapper_signal_trap_is_owned \
        "$_ITERM2_API_WRAPPER_SIGNAL_NAME" \
        "$trap_dump"; then
        command rm -f -- \
            "$trap_dump" \
            "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/binding" \
            "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/busy"
        return 0
    fi

    command rm -f -- "$trap_dump"
    _iterm2_api_wrapper_signal_binding_payload

    _iterm2_api_wrapper_signal_publish \
        "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/binding" \
        "$REPLY" || return 1

    # Removing busy is the final readiness transition. Python will not submit
    # another request or bootstrap command while this marker exists.
    command rm -f -- "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/busy"
}

_iterm2_api_wrapper_signal_deactivate() {
    emulate -L zsh

    [[ -n ${_ITERM2_API_WRAPPER_SIGNAL_DIR-} ]] || return 0
    command rm -f -- "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/binding"
}

_iterm2_api_wrapper_signal_mark_busy() {
    emulate -L zsh

    local publish_status

    [[ ${_ITERM2_API_WRAPPER_SIGNAL_PID-} == $$ ]] || return 1
    [[ -d ${_ITERM2_API_WRAPPER_SIGNAL_DIR-} ]] || return 1
    [[ -n ${_ITERM2_API_WRAPPER_SIGNAL_NAME-} ]] || return 1

    _iterm2_api_wrapper_signal_busy_payload
    _iterm2_api_wrapper_signal_publish \
        "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/busy" \
        "$REPLY"
    publish_status=$?

    _iterm2_api_wrapper_signal_deactivate
    return $publish_status
}

_iterm2_api_wrapper_signal_is_available() {
    emulate -L zsh

    local signal_name=$1
    local trap_dump=$2
    local trap_function="TRAP${signal_name}"
    local line

    # Function-form traps are not listed by the trap builtin.
    (( ${+functions[$trap_function]} )) && return 1

    while IFS= read -r line; do
        [[ $line == *" ${signal_name}" ]] && return 1
    done < "$trap_dump"

    return 0
}

_iterm2_api_wrapper_refresh_prompt() {
    emulate -L zsh

    local hook hook_status
    local prompt_status=0
    local redraw_status=0

    if (( ${+functions[precmd]} )); then
        precmd
        hook_status=$?

        if (( hook_status != 0 && prompt_status == 0 )); then
            prompt_status=$hook_status
        fi
    fi

    for hook in "${precmd_functions[@]}"; do
        [[ $hook == _iterm2_api_wrapper_signal_activate ]] && continue
        (( ${+functions[$hook]} )) || continue

        "$hook"
        hook_status=$?

        if (( hook_status != 0 && prompt_status == 0 )); then
            prompt_status=$hook_status
        fi
    done

    if zle >/dev/null 2>&1; then
        zle reset-prompt
        redraw_status=$?

        zle -R

        if (( redraw_status == 0 )); then
            redraw_status=$?
        fi
    fi

    REPLY="${prompt_status}"$'\t'"${redraw_status}"
}

_iterm2_api_wrapper_select_signal() {
    emulate -L zsh

    local signal_dir=$1
    local trap_dump=$2
    local signal_name=

    [[ -d $signal_dir ]] || return 1

    if [[ ${_ITERM2_API_WRAPPER_SIGNAL_PID-} == $$ &&
          ${_ITERM2_API_WRAPPER_SIGNAL_DIR-} == $signal_dir &&
          -n ${_ITERM2_API_WRAPPER_SIGNAL_NAME-} ]] &&
       _iterm2_api_wrapper_signal_trap_is_owned \
           "$_ITERM2_API_WRAPPER_SIGNAL_NAME" \
           "$trap_dump"; then
        signal_name=$_ITERM2_API_WRAPPER_SIGNAL_NAME
    elif _iterm2_api_wrapper_signal_is_available USR1 "$trap_dump"; then
        signal_name=USR1
    elif _iterm2_api_wrapper_signal_is_available USR2 "$trap_dump"; then
        signal_name=USR2
    fi

    REPLY=$signal_name
}

# Dispatch is sourced directly by a list-form trap. Keeping this block at
# sourced-file top level gives request programs the same scope as commands
# entered at the interactive prompt; in particular, typeset and option changes
# are not localized to an ordinary dispatcher function.
if [[ ${1-} == --dispatch ]]; then
    if [[ ${_ITERM2_API_WRAPPER_SIGNAL_PID-} != $$ ||
          ! -d ${_ITERM2_API_WRAPPER_SIGNAL_DIR-} ]]; then
        return 0
    fi

    _iterm2_api_wrapper_signal_mark_busy || return 0

    typeset -ga _iterm2_api_wrapper_dispatch_requests
    typeset -g _iterm2_api_wrapper_dispatch_request
    typeset -g _iterm2_api_wrapper_dispatch_nonce
    typeset -g _iterm2_api_wrapper_dispatch_started
    typeset -g _iterm2_api_wrapper_dispatch_response
    typeset -g _iterm2_api_wrapper_dispatch_stdout
    typeset -g _iterm2_api_wrapper_dispatch_stderr
    typeset -g _iterm2_api_wrapper_dispatch_payload
    typeset -g _iterm2_api_wrapper_dispatch_command_status
    typeset -g _iterm2_api_wrapper_dispatch_prompt_status
    typeset -g _iterm2_api_wrapper_dispatch_redraw_status

    _iterm2_api_wrapper_dispatch_requests=(
        "${_ITERM2_API_WRAPPER_SIGNAL_DIR}"/request."$$".*(N)
    )

    for _iterm2_api_wrapper_dispatch_request in "${_iterm2_api_wrapper_dispatch_requests[@]}"; do
        _iterm2_api_wrapper_dispatch_nonce=${_iterm2_api_wrapper_dispatch_request:t}
        _iterm2_api_wrapper_dispatch_nonce=${_iterm2_api_wrapper_dispatch_nonce##*.}

        if (( ${#_iterm2_api_wrapper_dispatch_nonce} != 32 )) ||
           [[ $_iterm2_api_wrapper_dispatch_nonce == *[^0-9a-f]* ]]; then
            command rm -f -- "$_iterm2_api_wrapper_dispatch_request"
            continue
        fi

        _iterm2_api_wrapper_dispatch_started="${_ITERM2_API_WRAPPER_SIGNAL_DIR}/started.$$.${_iterm2_api_wrapper_dispatch_nonce}"
        _iterm2_api_wrapper_dispatch_response="${_ITERM2_API_WRAPPER_SIGNAL_DIR}/response.$$.${_iterm2_api_wrapper_dispatch_nonce}"
        _iterm2_api_wrapper_dispatch_stdout="${_ITERM2_API_WRAPPER_SIGNAL_DIR}/stdout.$$.${_iterm2_api_wrapper_dispatch_nonce}"
        _iterm2_api_wrapper_dispatch_stderr="${_ITERM2_API_WRAPPER_SIGNAL_DIR}/stderr.$$.${_iterm2_api_wrapper_dispatch_nonce}"
        _iterm2_api_wrapper_dispatch_command_status=0
        _iterm2_api_wrapper_dispatch_prompt_status=0
        _iterm2_api_wrapper_dispatch_redraw_status=0

        _iterm2_api_wrapper_dispatch_payload="${_ITERM2_API_WRAPPER_SIGNAL_PROTOCOL}"$'\t'"started"$'\t'"$$"$'\t'"${_iterm2_api_wrapper_dispatch_nonce}"

        if _iterm2_api_wrapper_signal_publish \
            "$_iterm2_api_wrapper_dispatch_started" \
            "$_iterm2_api_wrapper_dispatch_payload"; then
            builtin source "$_iterm2_api_wrapper_dispatch_request" \
                </dev/null \
                >| "$_iterm2_api_wrapper_dispatch_stdout" \
                2>| "$_iterm2_api_wrapper_dispatch_stderr"
            _iterm2_api_wrapper_dispatch_command_status=$?
        else
            _iterm2_api_wrapper_dispatch_command_status=74
        fi

        command rm -f -- "$_iterm2_api_wrapper_dispatch_request"

        _iterm2_api_wrapper_refresh_prompt
        _iterm2_api_wrapper_dispatch_prompt_status=${REPLY%%$'\t'*}
        _iterm2_api_wrapper_dispatch_redraw_status=${REPLY#*$'\t'}

        _iterm2_api_wrapper_dispatch_payload="${_ITERM2_API_WRAPPER_SIGNAL_PROTOCOL}"$'\t'"ok"$'\t'"$$"$'\t'"${_iterm2_api_wrapper_dispatch_nonce}"$'\t'"${_iterm2_api_wrapper_dispatch_command_status}"$'\t'"${_iterm2_api_wrapper_dispatch_prompt_status}"$'\t'"${_iterm2_api_wrapper_dispatch_redraw_status}"

        _iterm2_api_wrapper_signal_publish \
            "$_iterm2_api_wrapper_dispatch_response" \
            "$_iterm2_api_wrapper_dispatch_payload"
    done

    unset _iterm2_api_wrapper_dispatch_requests \
        _iterm2_api_wrapper_dispatch_request \
        _iterm2_api_wrapper_dispatch_nonce \
        _iterm2_api_wrapper_dispatch_started \
        _iterm2_api_wrapper_dispatch_response \
        _iterm2_api_wrapper_dispatch_stdout \
        _iterm2_api_wrapper_dispatch_stderr \
        _iterm2_api_wrapper_dispatch_payload \
        _iterm2_api_wrapper_dispatch_command_status \
        _iterm2_api_wrapper_dispatch_prompt_status \
        _iterm2_api_wrapper_dispatch_redraw_status

    # Publish or withdraw readiness only after all request state is cleaned.
    # This must remain the last operation before returning from the trap.
    _iterm2_api_wrapper_signal_activate
    return 0
fi

if (( $# != 3 )); then
    print -u2 -r -- \
        "usage: source iterm2-signal.zsh SIGNAL_DIR NONCE HANDLER_DIGEST"
    return 64
fi

typeset _iterm2_api_wrapper_install_dir=$1
typeset _iterm2_api_wrapper_install_nonce=$2
typeset _iterm2_api_wrapper_install_digest=$3
typeset _iterm2_api_wrapper_install_ack="${_iterm2_api_wrapper_install_dir}/install.${_iterm2_api_wrapper_install_nonce}"
typeset _iterm2_api_wrapper_install_trap_dump="${_iterm2_api_wrapper_install_dir}/.traps.${_iterm2_api_wrapper_install_nonce}.$$"
typeset _iterm2_api_wrapper_install_signal=
typeset _iterm2_api_wrapper_install_payload

# Capturing trap output here avoids command substitution, which would inspect a
# subshell where ordinary signal traps have been reset.
trap >| "$_iterm2_api_wrapper_install_trap_dump"
_iterm2_api_wrapper_select_signal \
    "$_iterm2_api_wrapper_install_dir" \
    "$_iterm2_api_wrapper_install_trap_dump"
_iterm2_api_wrapper_install_signal=$REPLY
command rm -f -- "$_iterm2_api_wrapper_install_trap_dump"

if [[ -z $_iterm2_api_wrapper_install_signal ]]; then
    _iterm2_api_wrapper_install_payload="${_ITERM2_API_WRAPPER_SIGNAL_PROTOCOL}"$'\t'"error"$'\t'"$$"$'\t'"-"$'\t'"${_iterm2_api_wrapper_install_nonce}"$'\t'"${_iterm2_api_wrapper_install_digest}"$'\t'"Both SIGUSR1 and SIGUSR2 already have handlers"

    _iterm2_api_wrapper_signal_publish \
        "$_iterm2_api_wrapper_install_ack" \
        "$_iterm2_api_wrapper_install_payload"

    unset _iterm2_api_wrapper_install_dir \
        _iterm2_api_wrapper_install_nonce \
        _iterm2_api_wrapper_install_digest \
        _iterm2_api_wrapper_install_ack \
        _iterm2_api_wrapper_install_trap_dump \
        _iterm2_api_wrapper_install_signal \
        _iterm2_api_wrapper_install_payload

    return 1
fi

typeset -g _ITERM2_API_WRAPPER_SIGNAL_PID=$$
typeset -g _ITERM2_API_WRAPPER_SIGNAL_DIR=$_iterm2_api_wrapper_install_dir
typeset -g _ITERM2_API_WRAPPER_SIGNAL_NAME=$_iterm2_api_wrapper_install_signal
typeset -g _ITERM2_API_WRAPPER_SIGNAL_HANDLER_DIGEST=$_iterm2_api_wrapper_install_digest
typeset -g _ITERM2_API_WRAPPER_SIGNAL_GENERATION=$_iterm2_api_wrapper_install_nonce
typeset -g _ITERM2_API_WRAPPER_SIGNAL_HANDLER="${${(%):-%N}:A}"

# Output contents of interactive CLI commands without entering (e.g., git log)
typeset -gx PAGER=cat
typeset -gx GIT_PAGER=cat
typeset -gx MANPAGER=cat
typeset -gx BAT_PAGER=cat
typeset -gx LESS=FRX

# A list-form trap executes in the top-level environment where it was
# registered. The request itself is sourced by the dispatch block above.
trap 'builtin source "${_ITERM2_API_WRAPPER_SIGNAL_HANDLER}" --dispatch' \
    "$_iterm2_api_wrapper_install_signal"

autoload -Uz add-zsh-hook

add-zsh-hook -d preexec _iterm2_api_wrapper_signal_deactivate 2>/dev/null
add-zsh-hook -d preexec _iterm2_api_wrapper_signal_mark_busy 2>/dev/null
add-zsh-hook preexec _iterm2_api_wrapper_signal_mark_busy

add-zsh-hook -d precmd _iterm2_api_wrapper_signal_activate 2>/dev/null
add-zsh-hook precmd _iterm2_api_wrapper_signal_activate

add-zsh-hook -d zshexit _iterm2_api_wrapper_signal_deactivate 2>/dev/null
add-zsh-hook zshexit _iterm2_api_wrapper_signal_deactivate

_iterm2_api_wrapper_signal_activate

_iterm2_api_wrapper_install_payload="${_ITERM2_API_WRAPPER_SIGNAL_PROTOCOL}"$'\t'"ok"$'\t'"$$"$'\t'"${_iterm2_api_wrapper_install_signal}"$'\t'"${_iterm2_api_wrapper_install_nonce}"$'\t'"${_iterm2_api_wrapper_install_digest}"

_iterm2_api_wrapper_signal_publish \
    "$_iterm2_api_wrapper_install_ack" \
    "$_iterm2_api_wrapper_install_payload"

unset _iterm2_api_wrapper_install_dir \
    _iterm2_api_wrapper_install_nonce \
    _iterm2_api_wrapper_install_digest \
    _iterm2_api_wrapper_install_ack \
    _iterm2_api_wrapper_install_trap_dump \
    _iterm2_api_wrapper_install_signal \
    _iterm2_api_wrapper_install_payload
