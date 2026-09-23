# SPDX-License-Identifier: Apache-2.0
"""Decides what the booking assistant does next, given the chat so far.

The live chat widget hands us the transcript as plain text - one line per
turn, prefixed User: or Assistant:, always ending on the customer - and we
answer with one of the eight actions the booking flow knows how to perform.
The reply engine then executes that action; this module never writes the
reply itself.

Five settings shape the call: which model answers, how many of the trailing
turns it is shown, which instruction wording leads the prompt, whether the
answer comes back as a bare action name or as JSON, and the sampling
temperature. The reply is parsed into exactly one of the eight actions;
anything else is a failed decision and is raised rather than guessed at,
because a guessed action is a booking made or cancelled on nobody's say-so.
"""

import json
import re

MODELS = ("claude-haiku-4-5", "claude-sonnet-4-6")

HISTORY_WINDOWS = (1, 3, 8)

PROMPT_STYLES = {
    "direct": "Read the chat and name the single next action the assistant should take.",
    "precedence": (
        "Read the whole chat before deciding. A request for a person, a complaint, "
        "a medical or accessibility need, or a party of ten or more goes to an agent "
        "before anything else; cancelling an existing booking comes before making a "
        "new one; a question about a rule is answered before a price is given; a "
        "quote needs a travel date first and a passenger count second; a customer "
        "who restates a date or a headcount differently is asked for it again. "
        "Then name the single next action."
    ),
}

OUTPUT_FORMATS = {
    "label": "Answer with the action name alone.",
    "json": 'Answer with {"action": "<action name>"} and nothing else.',
}

TEMPERATURES = (0.0, 0.4)

ACTIONS = (
    "ask_dates",
    "ask_passengers",
    "quote_fare",
    "confirm_booking",
    "offer_alternative",
    "explain_policy",
    "escalate_to_agent",
    "cancel_booking",
)

ACTION_LIST = ", ".join(ACTIONS)

ACTION_PATTERN = re.compile("|".join(ACTIONS))


def recent_turns(transcript, window):
    """The last `window` turns of the chat, oldest first."""
    turns = [line for line in transcript.splitlines() if line.strip()]
    return turns[-window:]


def build_prompt(transcript, config):
    """The request text, assembled from the settings that shape it."""
    window = config.get("history_window", 3)
    lines = [
        PROMPT_STYLES[config.get("prompt_style", "direct")],
        f"Actions: {ACTION_LIST}.",
        OUTPUT_FORMATS[config.get("output_format", "label")],
        "Chat:",
    ]
    for turn in recent_turns(transcript, window):
        lines.append(f"  {turn}")
    return "\n".join(lines)


def parse_reply(reply, output_format):
    """The action the model answered with, read the way this format writes it."""
    if output_format == "json":
        try:
            candidate = json.loads(reply)["action"]
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError(f"reply is not the object we asked for: {reply!r}") from error
    else:
        candidate = reply
    found = ACTION_PATTERN.search(str(candidate).strip().lower())
    if found is None:
        raise ValueError(f"no action name in {reply!r}")
    return found.group(0)


def call_model(model, prompt, temperature):
    """One completion from the model, at the sampling temperature asked for."""
    from anthropic import Anthropic

    answer = Anthropic().messages.create(
        model=model,
        max_tokens=48,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return answer.content[0].text


def run(input_text, config):
    model = config.get("model", "claude-haiku-4-5")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    window = config.get("history_window", 3)
    if window not in HISTORY_WINDOWS:
        raise ValueError(f"history window {window!r} is not one of {HISTORY_WINDOWS}")
    prompt_style = config.get("prompt_style", "direct")
    if prompt_style not in PROMPT_STYLES:
        raise ValueError(f"{prompt_style!r} is not one of the prompt styles we wrote")
    output_format = config.get("output_format", "label")
    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"{output_format!r} is not one of the answer formats we accept")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    return parse_reply(
        call_model(model, build_prompt(input_text, config), temperature), output_format
    )
