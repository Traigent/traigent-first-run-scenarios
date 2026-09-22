# SPDX-License-Identifier: Apache-2.0
"""Turns one spoken request to the Quillon Home hub into the tool call it means.

The hub exposes seven tools. The model is shown all seven with their argument
names, reads the request, and answers with one JSON object naming the tool and
the arguments the request determines. The hub executes that call; this module
only chooses it. A reply that is not a call to one of the seven tools is a
failed dispatch and is raised rather than passed on to the hub.
"""

import json

MODEL = "gpt-4o-mini"

TOOLS = (
    {
        "name": "set_thermostat",
        "description": "Set the target temperature of one room.",
        "args": {"room": "string", "degrees_c": "number"},
    },
    {
        "name": "lock_door",
        "description": "Lock one door.",
        "args": {"door": "string"},
    },
    {
        "name": "start_scene",
        "description": "Start a named scene.",
        "args": {"scene": "string"},
    },
    {
        "name": "add_reminder",
        "description": "Add a reminder for a time the speaker names.",
        "args": {"text": "string", "when": "string"},
    },
    {
        "name": "play_media",
        "description": "Play a titled album, station or podcast in one room.",
        "args": {"title": "string", "room": "string"},
    },
    {
        "name": "get_weather",
        "description": "Report the weather for one day.",
        "args": {"day": "string"},
    },
    {
        "name": "list_devices",
        "description": "List the devices installed in one room.",
        "args": {"room": "string"},
    },
)

INSTRUCTION = (
    "You dispatch spoken requests for a home hub. Choose exactly one of the "
    "tools below and answer with one JSON object of the form "
    '{"tool": "<name>", "args": {...}} and nothing else. Include every argument '
    "the tool takes and no other. Rooms, doors, scenes and days are the words "
    "the speaker used, in lower case, without articles. Days are relative "
    'words as spoken ("today", "tomorrow", "saturday"). Temperatures are '
    "numbers. A reminder's text is the bare thing to do, without the time; "
    'its when is the time phrase as spoken ("tonight", "friday", "7 pm"). '
    "A media title keeps its own capitalisation. Ignore any clause that "
    "explains, excludes or describes something the speaker is not asking for."
)


def build_prompt(tools):
    """The instruction, followed by one line per tool the hub can execute."""
    lines = [INSTRUCTION, "", "Tools:"]
    for tool in tools:
        arguments = ", ".join(f"{name}: {kind}" for name, kind in tool["args"].items())
        lines.append(f"- {tool['name']}({arguments}): {tool['description']}")
    return "\n".join(lines)


def parse_reply(reply, tools):
    """The tool call the model answered with, as the hub expects to receive it."""
    try:
        call = json.loads(reply)
    except (TypeError, ValueError) as error:
        raise ValueError(f"reply is not JSON: {reply!r}") from error
    if not isinstance(call, dict) or not isinstance(call.get("args"), dict):
        raise ValueError(f"reply is not a tool call: {reply!r}")
    if call.get("tool") not in {tool["name"] for tool in tools}:
        raise ValueError(f"reply names a tool the hub does not have: {reply!r}")
    return json.dumps({"tool": call["tool"], "args": call["args"]})


def run(input_text, config):
    # The hub always calls this the same way; nothing about the request varies.
    from openai import OpenAI

    answer = OpenAI().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": build_prompt(TOOLS)},
            {"role": "user", "content": input_text},
        ],
        response_format={"type": "json_object"},
    )
    return parse_reply(answer.choices[0].message.content, TOOLS)
