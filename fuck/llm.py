"""Ask Claude to diagnose the failed command and propose a fix."""

import json
from dataclasses import dataclass

import anthropic

SYSTEM = """\
You fix failed shell commands. You get the command the user just ran, its exit \
status, its output, and some environment details. Work out why it failed and \
propose one corrected command that does what the user intended.

Rules:
- The command must run as-is in the user's shell ({shell}). Chain steps with && \
if needed, e.g. install a missing tool and then rerun the original command.
- If the output is a tmux screen capture, it may contain unrelated earlier \
output; focus on the most recent run of the command.
- If the problem cannot be fixed by a shell command (e.g. a bug in the user's \
code), leave "command" empty and say what to change instead.
- Set "dangerous" to true if the command deletes data, force-pushes, rewrites \
history, changes system configuration, or is otherwise hard to undo.
- If a <user_hint> is given, it describes what the user wants and takes priority.
- "explanation": one to three short sentences of plain text (no markdown), \
written in {lang}.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {"type": "string"},
        "command": {"type": "string"},
        "dangerous": {"type": "boolean"},
    },
    "required": ["explanation", "command", "dangerous"],
    "additionalProperties": False,
}


@dataclass
class Fix:
    explanation: str
    command: str
    dangerous: bool


class LLMError(Exception):
    pass


def ask(
    context: str,
    *,
    shell: str,
    lang: str,
    model: str,
    effort: str,
    api_key: str,
    base_url: str,
) -> Fix:
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
    try:
        resp = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
            system=SYSTEM.format(shell=shell, lang=lang),
            messages=[{"role": "user", "content": context}],
        )
    except anthropic.AuthenticationError:
        raise LLMError("authentication failed: check api_key in the config")
    except anthropic.RateLimitError:
        raise LLMError("rate limited, try again in a moment")
    except anthropic.APIStatusError as e:
        raise LLMError(f"API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError as e:
        raise LLMError(f"cannot reach the API: {e}")

    if resp.stop_reason == "refusal":
        raise LLMError("the model declined to answer")
    if resp.stop_reason == "max_tokens":
        raise LLMError("the response was cut off (max_tokens)")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise LLMError(f"unexpected response: {text[:200]}")
    return Fix(data["explanation"], data["command"].strip(), data["dangerous"])
