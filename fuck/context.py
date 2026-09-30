"""Collect what the LLM needs to diagnose the failed command."""

import os
import platform
import shutil
import signal
import subprocess
from dataclasses import dataclass

HEAD_LINES = 60
TAIL_LINES = 300
TMUX_LINES = 300
MAX_CWD_ENTRIES = 100


@dataclass
class Context:
    command: str
    status: str
    shell: str
    history: str = ""
    output: str = ""
    output_source: str = ""
    hint: str = ""

    def render(self) -> str:
        parts = [
            f"<command>{self.command}</command>",
            f"<exit_status>{self.status or 'unknown'}</exit_status>",
            f"<shell>{self.shell}</shell>",
            f"<os>{os_name()}</os>",
            f"<cwd>{os.getcwd()}</cwd>",
            f"<cwd_entries>\n{cwd_entries()}\n</cwd_entries>",
        ]
        if self.history:
            parts.append(f"<recent_history>\n{self.history}\n</recent_history>")
        if self.output:
            parts.append(f'<output source="{self.output_source}">\n{self.output}\n</output>')
        else:
            parts.append("<output>not available</output>")
        if self.hint:
            parts.append(f"<user_hint>{self.hint}</user_hint>")
        return "\n".join(parts)


def os_name() -> str:
    if platform.system() == "Darwin":
        return f"macOS {platform.mac_ver()[0]}"
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return f"{platform.system()} {platform.release()}"


def cwd_entries() -> str:
    try:
        names = sorted(os.listdir("."))
    except OSError as e:
        return f"(cannot list: {e})"
    shown = [n + "/" if os.path.isdir(n) else n for n in names[:MAX_CWD_ENTRIES]]
    if len(names) > MAX_CWD_ENTRIES:
        shown.append(f"... and {len(names) - MAX_CWD_ENTRIES} more")
    return "\n".join(shown)


def truncate(text: str) -> str:
    """Keep the head (first errors) and tail (last errors) of long output."""
    lines = text.rstrip().splitlines()
    if len(lines) <= HEAD_LINES + TAIL_LINES:
        return "\n".join(lines)
    skipped = len(lines) - HEAD_LINES - TAIL_LINES
    return "\n".join(lines[:HEAD_LINES] + [f"[... {skipped} lines omitted ...]"] + lines[-TAIL_LINES:])


def tmux_capture() -> str | None:
    """Read the current tmux pane, which already shows the failed command's output."""
    if not os.environ.get("TMUX") or not shutil.which("tmux"):
        return None
    args = ["tmux", "capture-pane", "-p", "-J", "-S", f"-{TMUX_LINES}"]
    if pane := os.environ.get("TMUX_PANE"):
        args += ["-t", pane]
    try:
        r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.rstrip() if r.returncode == 0 else None


def rerun(command: str, shell: str, timeout: float) -> str:
    """Run the command again to capture its output, like thefuck does.

    An interactive shell is used so the user's aliases and functions resolve.
    """
    p = subprocess.Popen(
        [shutil.which(shell) or "sh", "-ic", command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        out += f"\n[killed after {timeout:g}s timeout]"
    return truncate(out)
