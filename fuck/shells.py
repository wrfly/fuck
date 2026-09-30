"""Shell integration scripts, printed by `fuck --init <shell>`.

The hooks remember the last command line and its exit status. The `fuck`
function passes them to the Python CLI through env vars, then evals the
fixed command (written to a temp file) in the current shell so `cd`,
`export` etc. take effect.
"""

ZSH = r"""
__fuck_preexec() { __fuck_pending=$1 }
__fuck_precmd() {
  local s=$?
  if [[ -n $__fuck_pending && ${${(z)__fuck_pending}[1]} != fuck ]]; then
    __fuck_cmd=$__fuck_pending
    __fuck_status=$s
  fi
  __fuck_pending=
  return $s
}
autoload -Uz add-zsh-hook
add-zsh-hook preexec __fuck_preexec
# run first, so $? is still the status of the user's command
precmd_functions=(__fuck_precmd ${precmd_functions:#__fuck_precmd})

fuck() {
  local out ret cmd
  out=$(mktemp "${TMPDIR:-/tmp}/fuck.XXXXXX") || return 1
  FUCK_CMD=$__fuck_cmd FUCK_STATUS=$__fuck_status FUCK_SHELL=zsh \
    FUCK_HISTORY="$(fc -ln -20 2>/dev/null)" FUCK_OUT=$out command fuck "$@"
  ret=$?
  cmd=$(<$out)
  rm -f -- $out
  [[ -n $cmd ]] || return $ret
  print -s -- "$cmd"
  eval "$cmd"
  ret=$?
  __fuck_cmd=$cmd
  __fuck_status=$ret
  return $ret
}
"""

BASH = r"""
__fuck_prompt() {
  local s=$? line re='^ *([0-9]+)\*? +(.*)$'
  line=$(HISTTIMEFORMAT= builtin history 1)
  if [[ $line =~ $re && ${BASH_REMATCH[1]} != "$__fuck_histnum" ]]; then
    __fuck_histnum=${BASH_REMATCH[1]}
    line=${BASH_REMATCH[2]}
    if [[ ${line%% *} != fuck ]]; then
      __fuck_cmd=$line
      __fuck_status=$s
    fi
  fi
  return $s
}
if [[ $(declare -p PROMPT_COMMAND 2>/dev/null) == "declare -a"* ]]; then
  PROMPT_COMMAND=(__fuck_prompt "${PROMPT_COMMAND[@]}")
else
  PROMPT_COMMAND="__fuck_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fi
# don't treat the last command of a previous session as the one to fix
__fuck_prompt; __fuck_cmd=; __fuck_status=

fuck() {
  local out ret cmd
  out=$(mktemp "${TMPDIR:-/tmp}/fuck.XXXXXX") || return 1
  FUCK_CMD=$__fuck_cmd FUCK_STATUS=$__fuck_status FUCK_SHELL=bash \
    FUCK_HISTORY="$(HISTTIMEFORMAT= builtin history 20)" FUCK_OUT=$out command fuck "$@"
  ret=$?
  cmd=$(<"$out")
  rm -f -- "$out"
  [[ -n $cmd ]] || return $ret
  history -s -- "$cmd"
  eval "$cmd"
}
"""

SCRIPTS = {"zsh": ZSH, "bash": BASH}
