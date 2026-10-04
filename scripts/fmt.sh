#!/usr/bin/env zsh

set -eo pipefail

typeset -g project_root
project_root="$(pwd)"

typeset -g -a ruffArgs
ruffArgs=(format)
typeset -g command_name
command_name=fmt

_getRelPath() {
  local file_path relpath
  file_path="$1"
  relpath="${file_path#$project_root/}"
  print -r -- "$relpath"
}

# Ruff's check output supplies changed filenames; verbose logs also supply
# all formatter-selected paths (including formatter-specific exclusions).
_checkFormat() {
  local exit_code=0
  check_output=$(NO_COLOR=1 ruff "${ruffArgs[@]}" --check --output-format concise --verbose 2>&1) || exit_code=$?

  # Exit 1 means files need formatting, not that the command failed.
  if (( exit_code > 1 )); then
    print -r -- "$check_output" >&2
    return "$exit_code"
  fi
}

_changedPaths() {
  print -r -- "$check_output" |
    rg --pcre2 '^(.*):\d+:\d+: unformatted: File would be reformatted$|^Would reformat: (.*)$' --replace='$1$2' |
    awk '!seen[$0]++' || true
}

callFmt() {
  local check_output output format_output exit_code=0
  _checkFormat || return $?
  output=$(_changedPaths)

  format_output=$(ruff "${ruffArgs[@]}" 2>&1) || exit_code=$?
  if (( exit_code != 0 )); then
    print -r -- "$format_output" >&2
    return "$exit_code"
  fi

  if [[ -n "$output" ]]; then
    print -r -- "$output" | while IFS= read -r file_path; do
      rel_path=`_getRelPath "$file_path"`
      echo "✔︎ ${c_fggreen}Formatted${c_reset}: ${c_fgcyan}${c_bold}${c_underline}/${rel_path}${c_reset}"
    done
  else
    echo "${c_fgyellow}No files needed formatting.${c_reset}"
  fi
}

callCheck() {
  local check_output output
  _checkFormat || return $?
  output=$(_changedPaths)

  if [[ -n "$output" ]]; then
    print -r -- "$output" | while IFS= read -r file_path; do
      rel_path=`_getRelPath "$file_path"`
      echo "✔︎ ${c_italic}${c_fgorange}Format?${c_reset}: ${c_fgcyan}${c_bold}${c_underline}/${rel_path}${c_reset}"
    done
  else
    echo "${c_fgyellow}No files needed formatting.${c_reset}"
  fi
}

callOutput() {
  local check_output paths file_path rel_path decimalPlaces index curDecimalPlaces suffix
  local -a output
  _checkFormat || return $?
  paths=$(
    print -r -- "$check_output" |
      rg --pcre2 '^.*\[ruff::commands::format\]\[DEBUG\] format_path; path=(.*)$' --replace='$1' |
      sort -u
  ) || true
  output=("${(@f)paths}")

  if [[ -n "$paths" ]]; then
    decimalPlaces=$(( ${#${#output}} - 1 ))
    index=1
    print -rl -- "${output[@]}" | while IFS= read -r file_path; do
      curDecimalPlaces=$(( ${#index} ))
      suffix=''
      while (( ${#suffix} < decimalPlaces - curDecimalPlaces + 1 )); do
        suffix+=' '
      done
      rel_path=`_getRelPath "$file_path"`
      echo "$suffix$index. ${c_fggreen}✔︎${c_reset} ${c_fgcyan}${c_bold}${c_underline}/${rel_path}${c_reset}"

      (( ++index ))
    done
  else
    echo "${c_fgyellow}No files needed formatting.${c_reset}"
  fi
}

# $# = number of arguments passed
# $@ = arguments as list
# ${<array_var>[(Ie)<string>]} = retrieve index of matched string in array
if (( $# > 0 )); then
  firstArg="$1"

  case "$firstArg" in
    fmt|format|check|help|output-file-paths|file-paths|output)
      command_name="$firstArg"
      ruffArgs=("$@")
      ruffArgs[1]=format
      echo "command_name: $command_name | ruffArgs: $ruffArgs[@]"
      ;;
    *)
      ruffArgs+=("$@")
      ;;
  esac
fi

# printf 'Received %d argument(s):\n' "$#"
# printf '  %q\n' "$@"

# printf 'Running ruff with %d argument(s):\n' "$(( ${#ruffArgs[@]} + $# ))"
# printf 'Running ruff with %d argument(s):\n' "${#ruffArgs[@]}"
# printf '  %q\n' "${ruffArgs[@]}"
# printf '\n'

case "$command_name" in
  fmt | format)
    callFmt
    ;;
  check)
    callCheck
    ;;
  output-file-paths | file-paths | output)
    callOutput
    ;;
  help)
    ruffArgs[1]=help
    if (( ${#ruffArgs[@]} == 1 )); then
      ruffArgs+=(format)
    fi
    ruff "${ruffArgs[@]}"
    ;;
  *)
    printf 'Unsupported formatter command: %s\n' "$command_name" >&2
    exit 1
    ;;
esac
