# SPDX-License-Identifier: Apache-2.0
"""Quotes a road-freight job from a plain-English shipment description.

The quoting desk pastes the customer's message in and gets one number back: the
price in whole currency units under our current tariff. Four settings shape the
call: which model works the quote, whether it answers with the number alone or
shows its working first, which reminder about units rides with the request, and
how much the model is allowed to vary between runs. The tariff goes in as the
first system message on every call, so the model applies our prices rather than
recalling them. The reply is read for the last number in it; a reply with no
number in it is a failed quote and is raised rather than guessed at.
"""

import re

from litellm import completion

MODELS = (
    "openrouter/openai/gpt-4o-mini",
    "openrouter/anthropic/claude-3.5-haiku",
    "openrouter/google/gemini-2.0-flash-001",
)

PROMPT_STYLES = {
    "direct": "Reply with the quoted price alone, as one whole number.",
    "worked": "Show the working one step per line, then put the final quoted price on its own last line as one whole number.",
}

UNITS_HINTS = {
    "plain": "Write the price as a plain number: no currency symbol, no thousands separator, no decimals.",
    "reminder": "Weights are in kilograms, dimensions in centimetres and distances in kilometres; the price is in whole currency units, so round it to the nearest unit at the end.",
}

TEMPERATURES = (0.0, 0.3)

TARIFF = """Tamsin Freight road tariff, current edition.
1. Base fee: 45 per shipment.
2. Dimensional weight in kg = length x width x height in cm, divided by 5000, rounded UP to the next whole kilogram. Chargeable weight is the greater of the actual weight and the dimensional weight.
3. Weight charge: 0.90 per chargeable kilogram.
4. Distance charge: 0.35 per kilometre.
5. Subtotal = base fee + weight charge + distance charge.
6. Service class multiplier on the subtotal: standard x 1.0, express x 1.5.
7. Surcharges, applied after the class multiplier and in this order: hazardous goods add 20% of the class-adjusted amount; residential delivery then adds a flat 30.
8. Round the final figure to the nearest whole unit (halves round up). That whole number is the quote."""

NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def call_model(model, messages, temperature):
    """One completion through OpenRouter, returned as the reply text."""
    answer = completion(model=model, messages=messages, temperature=temperature)
    return answer.choices[0].message.content


def parse_reply(reply):
    """The last number in the reply, which is where every style puts the quote."""
    found = NUMBER_PATTERN.findall(str(reply))
    if not found:
        raise ValueError(f"no number in the reply: {reply!r}")
    return float(found[-1].replace(",", ""))


def run(input_text, config):
    model = config.get("model", "openrouter/openai/gpt-4o-mini")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    prompt_style = config.get("prompt_style", "direct")
    if prompt_style not in PROMPT_STYLES:
        raise ValueError(f"prompt style {prompt_style!r} is not one of {tuple(PROMPT_STYLES)}")
    units_hint = config.get("units_hint", "plain")
    if units_hint not in UNITS_HINTS:
        raise ValueError(f"units hint {units_hint!r} is not one of {tuple(UNITS_HINTS)}")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    return parse_reply(
        call_model(
            model,
            [
                {"role": "system", "content": TARIFF},
                {"role": "system", "content": PROMPT_STYLES[prompt_style]},
                {"role": "system", "content": UNITS_HINTS[units_hint]},
                {"role": "user", "content": f"Shipment: {input_text}"},
            ],
            temperature,
        )
    )
