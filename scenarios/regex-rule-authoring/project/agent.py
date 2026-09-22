# SPDX-License-Identifier: Apache-2.0
"""Writes the redaction rule for a log line, for the Ferrowick logging desk.

The desk keeps a rule file: each entry is one Python regular expression that
matches the secret-looking part of a log line so the shipper can mask it before
the line leaves the building. An engineer describes the shape in a sentence and
this writes the expression. Four settings shape the call: which model writes the
rule, how the instruction is phrased, whether the reply is asked for bare or in
a code fence, and how much the model is allowed to vary between runs. The reply
is read for the expression, with a fence stripped if one came back; a reply with
nothing in it is a failed rule and is raised rather than guessed at.
"""

import re

from litellm import completion

MODELS = (
    "gpt-4o-mini",
    "claude-3-5-haiku-latest",
)

PROMPT_STYLES = {
    "plain": "Write one Python regular expression that matches what is described.",
    "anchored": (
        "Write one Python regular expression that matches what is described. "
        "Anchor it where the description implies an anchor."
    ),
    "explained": (
        "Write one Python regular expression that matches what is described. "
        "Think about the boundaries first, then give the expression on its own line."
    ),
}

FLAVOURS = {
    "bare": "Return the expression and nothing else.",
    "fenced": "Return the expression in a fenced code block and nothing else.",
}

TEMPERATURES = (0.0, 0.3)

FENCE = re.compile(r"```(?:[a-z]*\n)?(.*?)```", re.DOTALL)


def call_model(model, messages, temperature):
    """One completion, returned as the reply text."""
    answer = completion(model=model, messages=messages, temperature=temperature)
    return answer.choices[0].message.content


def parse_reply(reply):
    """The expression the reply carries, with a code fence removed if there is one."""
    text = str(reply).strip()
    fenced = FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    first = text.splitlines()[0].strip() if text else ""
    if not first:
        raise ValueError(f"no expression in the reply: {reply!r}")
    return first


def run(input_text, config):
    model = config.get("model", "gpt-4o-mini")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    prompt_style = config.get("prompt_style", "plain")
    if prompt_style not in PROMPT_STYLES:
        raise ValueError(f"prompt style {prompt_style!r} is not one of {tuple(PROMPT_STYLES)}")
    flavour = config.get("flavour", "bare")
    if flavour not in FLAVOURS:
        raise ValueError(f"flavour {flavour!r} is not one of {tuple(FLAVOURS)}")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    return parse_reply(
        call_model(
            model,
            [
                {"role": "system", "content": PROMPT_STYLES[prompt_style]},
                {"role": "system", "content": FLAVOURS[flavour]},
                {"role": "user", "content": f"Shape: {input_text}"},
            ],
            temperature,
        )
    )
