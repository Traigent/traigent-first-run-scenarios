# SPDX-License-Identifier: Apache-2.0
"""Turns a raw engineering-meeting transcript into the short summary that goes out afterwards.

Four settings shape the call: which model answers it (all routed through OpenRouter, so one key
covers every provider we compare), how long the summary is allowed to be, whether it comes back as
bullets or as prose, and how much the model is allowed to vary its wording. The reply is the
summary itself; an empty reply is a failed run and is raised rather than sent out as a blank mail.
"""

import litellm

MODELS = (
    "openrouter/openai/gpt-4o-mini",
    "openrouter/anthropic/claude-3.5-haiku",
    "openrouter/google/gemini-2.0-flash-001",
)

LENGTHS = {
    "brief": "Keep the summary to two or three sentences.",
    "full": "Write up to six sentences, giving each decision and each action item its own sentence.",
}

STYLES = {
    "prose": "Write the summary as running prose, with no bullet points or headings.",
    "bullets": "Write the summary as bullet points, one per decision or action item, each starting with the owner's name.",
}

TEMPERATURES = (0.0, 0.7)

TASK = (
    "You summarise engineering meetings at Corvid Analytics for people who were not there. "
    "State every decision that was made and who owns each follow-up. "
    "If a decision was reversed during the meeting, report only the final position. "
    "Leave out small talk and any proposal that was raised but not decided."
)


def build_prompt(transcript, config):
    """The request text, assembled from the two settings that shape its wording."""
    lines = [
        LENGTHS[config.get("length", "brief")],
        STYLES[config.get("style", "prose")],
    ]
    lines.append(f"{TASK}\n\nTranscript:\n{transcript}")
    return "\n\n".join(lines)


def call_model(model, prompt, temperature):
    """One completion through OpenRouter for whichever model was chosen."""
    reply = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return reply.choices[0].message.content


def clean_reply(reply):
    """The summary as sent, or a raised error when the model sent nothing back."""
    if not reply or not reply.strip():
        raise ValueError("the model returned an empty summary")
    return reply.strip()


def run(input_text, config):
    model = config.get("model", "openrouter/openai/gpt-4o-mini")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    return clean_reply(call_model(model, build_prompt(input_text, config), temperature))
