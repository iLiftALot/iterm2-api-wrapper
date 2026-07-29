typeset -g _ITERM2_API_WRAPPER_SIGNAL_PROTOCOL=2

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

_iterm2_api_wrapper_signal_activate() {
    emulate -L zsh

    local trap_function

    [[ ${_ITERM2_API_WRAPPER_SIGNAL_PID-} == $$ ]] || return 0
    [[ -d ${_ITERM2_API_WRAPPER_SIGNAL_DIR-} ]] || return 0
    [[ -n ${_ITERM2_API_WRAPPER_SIGNAL_NAME-} ]] || return 0

    trap_function="TRAP${_ITERM2_API_WRAPPER_SIGNAL_NAME}"

    if (( ! ${+functions[$trap_function]} )) ||
       [[ ${functions[$trap_function]} != *"_iterm2_api_wrapper_signal_dispatch"* ]]; then
        command rm -f -- \
            "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/binding"
        return 0
    fi

    _iterm2_api_wrapper_signal_binding_payload

    _iterm2_api_wrapper_signal_publish \
        "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/binding" \
        "$REPLY"
}

_iterm2_api_wrapper_signal_deactivate() {
    emulate -L zsh

    [[ -n ${_ITERM2_API_WRAPPER_SIGNAL_DIR-} ]] || return 0

    command rm -f -- \
        "${_ITERM2_API_WRAPPER_SIGNAL_DIR}/binding"
}

_iterm2_api_wrapper_signal_is_available() {
    emulate -L zsh

    local signal_name=$1
    local trap_dump=$2
    local trap_function="TRAP${signal_name}"
    local line

    # Function-form traps appear in the functions associative array.
    (( ${+functions[$trap_function]} )) && return 1

    # List-form traps registered with the trap builtin do not appear there.
    # The caller captured the listing at sourced-script top level because
    # command substitution would inspect a subshell with reset traps.
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
        (( ${+functions[$hook]} )) || continue

        "$hook"
        hook_status=$?

        if (( hook_status != 0 && prompt_status == 0 )); then
            prompt_status=$hook_status
        fi
    done

    # Revalidate only after every prompt hook has had a chance to run. If a
    # framework or user hook replaced our trap, this removes readiness rather
    # than leaving Python with a stale, potentially dangerous binding.
    _iterm2_api_wrapper_signal_activate

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

_iterm2_api_wrapper_signal_dispatch() {
    emulate -L zsh
    setopt local_options null_glob

    local request nonce target response payload
    local cd_status prompt_status redraw_status
    local -a requests

    # Only requests addressed to this exact shell PID are consumed.
    requests=(
        "${_ITERM2_API_WRAPPER_SIGNAL_DIR}"/request."$$".*(N)
    )

    for request in "${requests[@]}"; do
        nonce=${request:t}
        nonce=${nonce##*.}

        cd_status=0
        prompt_status=0
        redraw_status=0

        # NUL termination preserves every valid POSIX path byte except NUL,
        # including spaces and embedded/trailing newlines.
        if ! IFS= read -r -d $'\0' target < "$request"; then
            cd_status=64
        elif [[ ! -d $target ]]; then
            cd_status=66
        else
            builtin cd -- "$target"
            cd_status=$?
        fi

        command rm -f -- "$request"

        if (( cd_status == 0 )); then
            _iterm2_api_wrapper_refresh_prompt

            prompt_status=${REPLY%%$'\t'*}
            redraw_status=${REPLY#*$'\t'}
        fi

        # Publish only after cd, dynamic-prompt hooks, and any active ZLE
        # redraw have completed.
        response="${_ITERM2_API_WRAPPER_SIGNAL_DIR}/response.$$.${nonce}"
        payload="${_ITERM2_API_WRAPPER_SIGNAL_PROTOCOL}"$'\t'"ok"$'\t'"$$"$'\t'"${nonce}"$'\t'"${cd_status}"$'\t'"${prompt_status}"$'\t'"${redraw_status}"

        _iterm2_api_wrapper_signal_publish \
            "$response" \
            "$payload"
    done

    # Returning zero tells Zsh that the signal was handled.
    return 0
}

_iterm2_api_wrapper_select_signal() {
    emulate -L zsh

    local signal_dir=$1
    local trap_dump=$2
    local signal_name=
    local trap_function

    [[ -d $signal_dir ]] || return 1

    # Reuse our existing trap when it still belongs to this process and
    # session control directory.
    if [[ ${_ITERM2_API_WRAPPER_SIGNAL_PID-} == $$ &&
          ${_ITERM2_API_WRAPPER_SIGNAL_DIR-} == $signal_dir &&
          -n ${_ITERM2_API_WRAPPER_SIGNAL_NAME-} ]]; then
        trap_function="TRAP${_ITERM2_API_WRAPPER_SIGNAL_NAME}"

        if (( ${+functions[$trap_function]} )) &&
           [[ ${functions[$trap_function]} == *"_iterm2_api_wrapper_signal_dispatch"* ]]; then
            signal_name=$_ITERM2_API_WRAPPER_SIGNAL_NAME
        fi
    fi

    if [[ -z $signal_name ]]; then
        if _iterm2_api_wrapper_signal_is_available \
            USR1 \
            "$trap_dump"; then
            signal_name=USR1
        elif _iterm2_api_wrapper_signal_is_available \
            USR2 \
            "$trap_dump"; then
            signal_name=USR2
        fi
    fi

    REPLY=$signal_name
}

if (( $# != 3 )); then
    print -u2 -r -- \
        "usage: source iterm2-signal-cd.zsh SIGNAL_DIR NONCE HANDLER_DIGEST"
    return 64
fi

typeset _iterm2_api_wrapper_install_dir=$1
typeset _iterm2_api_wrapper_install_nonce=$2
typeset _iterm2_api_wrapper_install_digest=$3
typeset _iterm2_api_wrapper_install_ack="${_iterm2_api_wrapper_install_dir}/install.${_iterm2_api_wrapper_install_nonce}"
typeset _iterm2_api_wrapper_install_trap_dump="${_iterm2_api_wrapper_install_dir}/.traps.${_iterm2_api_wrapper_install_nonce}.$$"
typeset _iterm2_api_wrapper_install_signal=
typeset _iterm2_api_wrapper_install_trap_function
typeset _iterm2_api_wrapper_install_payload

# This must execute at sourced-script top level. Capturing trap through command
# substitution would inspect a subshell where list-form traps have been reset.
trap >| "$_iterm2_api_wrapper_install_trap_dump"

_iterm2_api_wrapper_select_signal \
    "$_iterm2_api_wrapper_install_dir" \
    "$_iterm2_api_wrapper_install_trap_dump"

_iterm2_api_wrapper_install_signal=$REPLY

command rm -f -- \
    "$_iterm2_api_wrapper_install_trap_dump"

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
        _iterm2_api_wrapper_install_trap_function \
        _iterm2_api_wrapper_install_payload

    return 1
fi

typeset -g _ITERM2_API_WRAPPER_SIGNAL_PID=$$
typeset -g _ITERM2_API_WRAPPER_SIGNAL_DIR=$_iterm2_api_wrapper_install_dir
typeset -g _ITERM2_API_WRAPPER_SIGNAL_NAME=$_iterm2_api_wrapper_install_signal
typeset -g _ITERM2_API_WRAPPER_SIGNAL_HANDLER_DIGEST=$_iterm2_api_wrapper_install_digest
typeset -g _ITERM2_API_WRAPPER_SIGNAL_GENERATION=$_iterm2_api_wrapper_install_nonce

# Trap registration must happen at the sourced script's top level. Zsh scopes
# traps created inside an ordinary function to that function.
_iterm2_api_wrapper_install_trap_function="TRAP${_iterm2_api_wrapper_install_signal}"
functions[$_iterm2_api_wrapper_install_trap_function]='_iterm2_api_wrapper_signal_dispatch "$@"'

autoload -Uz add-zsh-hook

# preexec withdraws readiness before a command can replace the trap. precmd
# republishes readiness only after the command returns and the trap is verified.
# Re-sourcing deletes then re-adds the hooks so duplicate hook entries do not
# accumulate.
add-zsh-hook -d \
    preexec \
    _iterm2_api_wrapper_signal_deactivate \
    2>/dev/null
add-zsh-hook \
    preexec \
    _iterm2_api_wrapper_signal_deactivate

add-zsh-hook -d \
    precmd \
    _iterm2_api_wrapper_signal_activate \
    2>/dev/null
add-zsh-hook \
    precmd \
    _iterm2_api_wrapper_signal_activate

add-zsh-hook -d \
    zshexit \
    _iterm2_api_wrapper_signal_deactivate \
    2>/dev/null
add-zsh-hook \
    zshexit \
    _iterm2_api_wrapper_signal_deactivate

# Publish readiness only after the top-level trap exists.
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
    _iterm2_api_wrapper_install_trap_function \
    _iterm2_api_wrapper_install_payload
