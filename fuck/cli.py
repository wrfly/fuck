"""fuck: type it after a failed command and let Claude fix it."""

import argparse
import itertools
import os
import re
import sys
import termios
import threading
import tty

from . import config, context, llm
from .shells import SCRIPTS

# our own invocations, in `fc -ln` (zsh) or numbered `history` (bash) format
SELF_IN_HISTORY = re.compile(r"^\s*(\d+\*?\s+)?fuck\b")


def color(code: str, text: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stderr.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def say(msg: str = "") -> None:
    print(msg, file=sys.stderr)


def default_lang(lang: str) -> str:
    if lang:
        return lang
    if os.environ.get("LANG", "").startswith("zh"):
        return "Simplified Chinese"
    return "the language of the user's hint if there is one, otherwise English"


class Spinner:
    def __init__(self, text: str):
        self.text = text
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.spin, daemon=True)

    def spin(self) -> None:
        for frame in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            sys.stderr.write(f"\r{color('36', frame)} {self.text}")
            sys.stderr.flush()
            if self.stop_event.wait(0.08):
                break
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def __enter__(self):
        if sys.stderr.isatty():
            self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join()


def getch() -> str:
    with open("/dev/tty", "rb", buffering=0) as f:
        fd = f.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return os.read(fd, 1).decode(errors="replace")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def edit(command: str) -> str:
    import readline

    readline.set_startup_hook(lambda: readline.insert_text(command))
    try:
        return input("edit> ").strip()
    finally:
        readline.set_startup_hook()


def confirm(fix: llm.Fix) -> str | None:
    """Return the command to run, or None to cancel."""
    command = fix.command
    while True:
        if fix.dangerous:
            say(color("1;31", "  ⚠ this command may be destructive"))
            say(f"  {color('2', '[y] run  [e] edit  [any other key] cancel')}")
        else:
            say(f"  {color('2', '[enter] run  [e] edit  [any other key] cancel')}")
        try:
            key = getch()
        except OSError:
            return None
        if key == "y" or (key in "\r\n" and not fix.dangerous):
            return command
        if key != "e":
            return None
        try:
            command = edit(command)
        except (EOFError, KeyboardInterrupt):
            say()
            return None
        if not command:
            return None
        say(f"{color('1;32', '➜')} {color('1', command)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fuck",
        description="Type `fuck` after a failed command and let Claude fix it.",
    )
    parser.add_argument("hint", nargs="*", help="optional hint, e.g. what you were trying to do")
    parser.add_argument("--init", metavar="SHELL", choices=sorted(SCRIPTS), help="print shell integration")
    parser.add_argument("-y", "--yes", action="store_true", help="run the fix without asking (unless dangerous)")
    parser.add_argument("--no-rerun", action="store_true", help="never re-run the command to capture its output")
    parser.add_argument("--dry-run", action="store_true", help="print what would be sent to the model and exit")
    parser.add_argument("--config", action="store_true", help="create the config file if missing and print its path")
    args = parser.parse_args()

    if args.init:
        print(SCRIPTS[args.init])
        return 0
    if args.config:
        print(config.create())
        return 0
    try:
        cfg = config.load()
    except config.ConfigError as e:
        say(f"fuck: {e}")
        return 1

    command = os.environ.get("FUCK_CMD", "").strip()
    shell = os.environ.get("FUCK_SHELL") or os.path.basename(os.environ.get("SHELL", "sh"))
    if not command and os.environ.get("FUCK_SHELL"):
        say("fuck: nothing to fix yet, run a command first")
        return 1
    if not command:
        say("fuck: shell integration is not loaded. Add this to your shell rc file and restart the shell:")
        say(f'  eval "$(command fuck --init {shell if shell in SCRIPTS else "zsh"})"')
        return 1

    ctx = context.Context(
        command=command,
        status=os.environ.get("FUCK_STATUS", ""),
        shell=shell,
        history="\n".join(
            line for line in os.environ.get("FUCK_HISTORY", "").splitlines()
            if line.strip() and not SELF_IN_HISTORY.match(line)
        ),
        hint=" ".join(args.hint),
    )
    if (screen := context.tmux_capture()) is not None:
        ctx.output, ctx.output_source = screen, "tmux screen capture"
    elif cfg.rerun and not args.no_rerun:
        with Spinner(f"re-running {command!r} to capture output"):
            ctx.output, ctx.output_source = context.rerun(command, shell, cfg.timeout), "re-run of the command"

    if args.dry_run:
        print(ctx.render())
        return 0
    if not cfg.api_key:
        say(f"fuck: set api_key in {config.create()}")
        return 1

    try:
        with Spinner("thinking"):
            fix = llm.ask(
                ctx.render(),
                shell=shell,
                lang=default_lang(cfg.lang),
                model=cfg.model,
                effort=cfg.effort,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
    except llm.LLMError as e:
        say(f"fuck: {e}")
        return 1
    except KeyboardInterrupt:
        return 130

    say(f"  {fix.explanation}")
    if not fix.command:
        return 1
    say(f"{color('1;32', '➜')} {color('1', fix.command)}")

    run = fix.command if args.yes and not fix.dangerous else confirm(fix)
    if not run:
        return 1

    if out := os.environ.get("FUCK_OUT"):
        with open(out, "w") as f:
            f.write(run)
    else:
        # called without the shell function: just print the fix
        print(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
