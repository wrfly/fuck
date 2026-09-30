"""Settings from ~/.config/fuck/config.toml."""

import dataclasses
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

TEMPLATE = """\
api_key = ""                              # required
# base_url = "https://api.anthropic.com"  # API endpoint or proxy
# model = "claude-opus-5-5"
# effort = "low"                          # low / medium / high / xhigh / max
# lang = "中文"                            # language of the explanation, defaults to $LANG
# rerun = true                            # re-run the command to capture output when not in tmux
# timeout = 10                            # re-run timeout in seconds
"""


@dataclass
class Config:
    api_key: str = ""
    base_url: str = "https://api.anthropic.com"
    model: str = "claude-opus-5-5"
    effort: str = "low"
    lang: str = ""
    rerun: bool = True
    timeout: float = 10.0


class ConfigError(Exception):
    pass


def path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "fuck" / "config.toml"


def create() -> Path:
    """Write the template if there is no config yet; return its path."""
    p = path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        # holds the API key
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(TEMPLATE)
    return p


def check(key: str, value, source: str):
    default = getattr(Config, key)
    if isinstance(default, bool):
        ok = isinstance(value, bool)
    elif isinstance(default, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        value = float(value) if ok else value
    else:
        ok = isinstance(value, str)
    if not ok:
        raise ConfigError(f"{source}: invalid value for {key}: {value!r}")
    return value


def load() -> Config:
    p = path()
    data = {}
    if p.exists():
        try:
            with p.open("rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{p}: {e}")
    fields = {f.name for f in dataclasses.fields(Config)}
    if unknown := set(data) - fields:
        raise ConfigError(f"{p}: unknown keys: {', '.join(sorted(unknown))}")

    cfg = Config()
    for key, value in data.items():
        setattr(cfg, key, check(key, value, str(p)))
    return cfg
