# SPDX-License-Identifier: Apache-2.0
"""Routes an inbound support ticket to the desk queue that should pick it up.

Four settings shape the call: which model answers it, which instruction wording
leads the prompt, how many worked examples are quoted before the ticket, and how
much the sampling is allowed to wander. The reply is parsed into one of the six
queue ids the desk runs; anything else is a failed routing and is raised rather
than guessed at, because a ticket dropped into the wrong queue sits there until
someone notices.
"""

import re

from openai import OpenAI

MODELS = ("gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1")

PROMPT_STYLES = {
    "plain": "Route this support ticket to the right queue.",
    "rules": (
        "Route this support ticket. billing is invoices, charges, seats, plans "
        "and refunds; access-and-login is sign-in, MFA, roles, invitations and "
        "locked accounts; integrations is any connection to another system, "
        "its feed, mapping, key or webhook; data-export is a report, download "
        "or generated file that is wrong; outage is the service failing for "
        "everyone; feature-request is a wish for something that does not exist."
    ),
    "precedence": (
        "Route this support ticket. When it raises more than one open issue, "
        "pick the highest of: outage, access-and-login, billing, integrations, "
        "data-export, feature-request. Something described as already resolved "
        "or needing no action is context, not an issue."
    ),
}

QUEUE_IDS = (
    "billing",
    "access-and-login",
    "integrations",
    "data-export",
    "outage",
    "feature-request",
)

FEW_SHOT_COUNTS = (0, 2, 4)

WORKED_EXAMPLES = (
    ("Our invoice lists a seat we removed in May.", "billing"),
    ("The nightly HR feed stopped creating new starters.", "integrations"),
    ("Nobody in the company can load any page since 08:00.", "outage"),
    ("Could the report builder remember my column choices?", "feature-request"),
)

TEMPERATURES = (0.0, 0.3, 0.7)

QUEUE_PATTERN = re.compile("|".join(re.escape(queue) for queue in QUEUE_IDS))


def build_prompt(ticket, config):
    """The request text, assembled from the two settings that shape it."""
    shots = config.get("few_shot_count", 0)
    if shots not in FEW_SHOT_COUNTS:
        raise ValueError(f"few-shot count {shots!r} is not one of {FEW_SHOT_COUNTS}")
    lines = [
        PROMPT_STYLES[config.get("prompt_style", "plain")],
        "Answer with the queue id alone: billing, access-and-login, integrations, "
        "data-export, outage, feature-request.",
    ]
    for example, queue in WORKED_EXAMPLES[:shots]:
        lines.append(f"Ticket: {example}\nQueue: {queue}")
    lines.append(f"Ticket: {ticket}")
    return "\n\n".join(lines)


def parse_reply(reply):
    """The queue id the model answered with, or an error when it gave none."""
    found = QUEUE_PATTERN.search(str(reply).lower())
    if found is None:
        raise ValueError(f"no queue id in {reply!r}")
    return found.group(0)


def call_model(model, prompt, temperature):
    """One completion from the desk's provider account."""
    answer = OpenAI().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return answer.choices[0].message.content


def run(input_text, config):
    model = config.get("model", "gpt-4.1-mini")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    return parse_reply(call_model(model, build_prompt(input_text, config), temperature))
