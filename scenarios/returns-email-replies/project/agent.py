# SPDX-License-Identifier: Apache-2.0
"""Drafts the reply our returns desk sends to an inbound customer email.

Four settings shape the call: which model writes the draft, the tone the desk
answers in, how long the reply should run, and how much the wording is allowed
to vary between drafts. The returns policy is quoted into every prompt so the
draft commits us to nothing the policy does not already say. The reply comes
back as plain text and is returned as written, for the person on the desk to
read before it goes out.
"""

from anthropic import Anthropic

MODELS = ("claude-sonnet-4-6", "claude-haiku-4-5")

TONES = {
    "warm": (
        "Write as a friendly person on the returns desk: acknowledge what the "
        "customer is dealing with, use plain words, and close by offering to "
        "help further."
    ),
    "concise": (
        "Write briefly and directly: state what we will do and what the "
        "customer needs to do next, and nothing else."
    ),
    "formal": (
        "Write in a courteous, formal register: full sentences, no "
        "contractions, and thank the customer for getting in touch."
    ),
}

LENGTHS = {
    "short": "Keep the reply under 80 words.",
    "full": "Write a complete reply of two to four short paragraphs.",
}

TEMPERATURES = (0.0, 0.6)

POLICY = (
    "Pellworth Outdoor returns policy. Unworn items with tags attached may be "
    "returned or exchanged within 30 days of delivery for a full refund to the "
    "original payment method; return postage is free with the prepaid label in "
    "the parcel. Between 31 and 60 days we exchange or issue store credit but do "
    "not refund. Items arriving damaged or faulty are replaced or refunded at "
    "any time within the 60-day window, and we ask for a photograph before "
    "issuing the label. Gifts bought from us can be exchanged or credited by the "
    "recipient with the gift receipt or order number, but a refund goes only to "
    "the original buyer. Footwear tried on indoors is returnable; footwear with "
    "outdoor wear is not. Manufacturing faults outside 60 days are handled under "
    "the two-year warranty, which covers materials and workmanship but not wear, "
    "abrasion or misuse. Clearance items marked final sale are not returnable "
    "unless faulty. Refunds are issued within five working days of the parcel "
    "reaching our warehouse."
)

SYSTEM_PROMPT = (
    "You draft replies for the Pellworth Outdoor returns desk. Answer only from "
    "the policy below and the customer's own email. Never invent order details, "
    "dates or promises the policy does not support. If the email is missing "
    "something we need, ask for it in the reply. Sign off as the Pellworth "
    "Outdoor returns team.\n\n"
    + POLICY
)


def build_prompt(email, config):
    """The request text, assembled from the two settings that shape wording."""
    lines = [
        TONES[config.get("tone", "warm")],
        LENGTHS[config.get("length", "full")],
    ]
    lines.append(f"Reply to this customer email:\n{email}")
    return "\n\n".join(lines)


def call_model(model, prompt, config):
    """One draft from the model the desk has chosen."""
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    answer = Anthropic().messages.create(
        model=model,
        max_tokens=1024,
        temperature=temperature,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return answer.content[0].text


def run(input_text, config):
    model = config.get("model", "claude-sonnet-4-6")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    return call_model(model, build_prompt(input_text, config), config)
