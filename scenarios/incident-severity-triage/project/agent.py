# SPDX-License-Identifier: Apache-2.0
"""Assigns a severity to an inbound incident report before a human picks it up.

Four settings shape the call: which model answers it, which instruction wording
leads the prompt, how many earlier incidents are quoted back as context, and
whether the answer comes back as a bare label or as JSON. The reply is parsed
into one of the four severities the incident review board recognises; anything
else is a failed triage and is raised rather than guessed at.
"""

import json
import re

MODELS = {
    "gpt-4o-mini": "openai",
    "gpt-4o": "openai",
    "claude-3-5-haiku-latest": "anthropic",
}

PROMPT_STYLES = {
    "plain": "Give the severity of this incident.",
    "step_by_step": "Work through blast radius, then customer impact, then answer.",
    "rubric": "Apply the rubric: SEV1 outage or data loss, SEV2 major degradation, SEV3 limited impact with a workaround, SEV4 cosmetic.",
}

CONTEXT_DEPTHS = (0, 2, 4)

PAST_INCIDENTS = (
    "2025-11-02 checkout timeouts for 40 minutes, closed SEV1",
    "2026-01-17 search results stale in one region, closed SEV3",
    "2026-03-08 password reset mail delayed by an hour, closed SEV2",
    "2026-05-21 contrast bug on the settings page, closed SEV4",
)

FORMAT_INSTRUCTIONS = {
    "label": "Answer with the severity label alone.",
    "json": 'Answer with {"severity": "<label>"} and nothing else.',
}

WORKED_EXAMPLES = (
    ("Payments API returns 503 for every checkout.", "SEV1"),
    ("Avatar images load slowly on the profile page.", "SEV4"),
)

SEVERITY_PATTERN = re.compile(r"SEV[1-4]")


def build_prompt(report, config):
    """The request text, assembled from the three settings that shape it."""
    depth = config.get("retrieval", 0)
    if depth not in CONTEXT_DEPTHS:
        raise ValueError(f"context depth {depth!r} is not one of {CONTEXT_DEPTHS}")
    lines = [
        PROMPT_STYLES[config.get("prompt_style", "plain")],
        FORMAT_INSTRUCTIONS[config.get("output_format", "label")],
    ]
    for example, severity in WORKED_EXAMPLES:
        lines.append(f"Report: {example}\nSeverity: {severity}")
    for incident in PAST_INCIDENTS[:depth]:
        lines.append(f"Earlier incident: {incident}")
    lines.append(f"Report: {report}")
    return "\n\n".join(lines)


def parse_reply(reply, config):
    """The severity the model answered with, read the way this format writes it."""
    if config.get("output_format", "label") == "json":
        try:
            candidate = json.loads(reply)["severity"]
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError(
                f"reply is not the object we asked for: {reply!r}"
            ) from error
    else:
        candidate = reply
    found = SEVERITY_PATTERN.search(str(candidate).upper())
    if found is None:
        raise ValueError(f"no severity label in {reply!r}")
    return found.group(0)


def call_model(model, prompt):
    """One completion from whichever provider serves this model."""
    if MODELS[model] == "anthropic":
        from anthropic import Anthropic

        answer = Anthropic().messages.create(
            model=model,
            max_tokens=32,
            messages=[{"role": "user", "content": prompt}],
        )
        return answer.content[0].text
    from openai import OpenAI

    answer = OpenAI().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return answer.choices[0].message.content


def run(input_text, config):
    model = config.get("model", "gpt-4o-mini")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    return parse_reply(call_model(model, build_prompt(input_text, config)), config)
