# SPDX-License-Identifier: Apache-2.0
"""Pulls the four lease facts the renewals desk tracks out of one clause excerpt.

For every lease on the Westbrook estate the desk keeps one record: who the
tenant is, how long the term runs in months, how many days of notice the
clause requires, and whether the lease renews by itself, only on request, or
not at all. Reading those out of the term-and-renewal clause by hand is slow
and the clauses are not written to a template, so this module asks a model to
do the first pass. Four settings shape the call: which model answers, which
instruction wording leads the prompt, whether the answer comes back as a JSON
object or as four `key: value` lines, and the sampling temperature. Either
answer shape is parsed back into the same four-field object; a reply that
leaves a field out is raised rather than filled in, because a blank on the
desk's record is a question and a guess is a mistake nobody will look for.
"""

import json
import re

MODELS = ("gpt-4o-mini", "gpt-4o")

PROMPT_STYLES = {
    "direct": "Extract the tenant, the term, the notice period and the renewal type from this lease clause.",
    "checklist": "Read the clause once for the parties, once for every duration, and once for what happens at expiry, then answer. Give the term in months and the notice period in days, converting years and weeks. Where a value is given by reference to another clause or schedule, use the figure the excerpt quotes for it. Where the clause states an exception and says its condition is met, the exception decides the renewal type.",
}

FORMAT_INSTRUCTIONS = {
    "json": 'Answer with one JSON object and nothing else, shaped exactly like {"tenant": "<name as written>", "term_months": <integer>, "notice_days": <integer>, "renewal": "<auto, manual or none>"}.',
    "lines": "Answer with exactly four lines and nothing else, one field per line, in the form tenant: <name as written>, term_months: <integer>, notice_days: <integer>, renewal: <auto, manual or none>.",
}

TEMPERATURES = (0.0, 0.3)

FIELDS = ("tenant", "term_months", "notice_days", "renewal")

RENEWAL_TYPES = ("auto", "manual", "none")

LINE_PATTERN = re.compile(r"^\s*[-*]?\s*\"?([a-z_]+)\"?\s*[:=]\s*(.+?)\s*$", re.IGNORECASE)


def build_prompt(clause, config):
    """The request text: the chosen instruction, the answer shape, then the clause."""
    lines = [
        PROMPT_STYLES[config.get("prompt_style", "direct")],
        FORMAT_INSTRUCTIONS[config.get("output_format", "json")],
        "The renewal type is auto when the lease continues by itself unless notice is served, manual when a renewal happens only on request or by signing a new lease, and none when the lease simply ends.",
    ]
    lines.append(f"Clause:\n{clause}")
    return "\n\n".join(lines)


def read_lines(reply):
    """The fields from a four-line reply, read as key: value pairs."""
    record = {}
    for line in reply.splitlines():
        match = LINE_PATTERN.match(line)
        if match:
            record[match.group(1).lower()] = match.group(2).strip().strip('",')
    return record


def read_json(reply):
    """The fields from a JSON reply, tolerating a code fence around the object."""
    text = reply.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        record = json.loads(text)
    except ValueError as error:
        raise ValueError(f"reply is not the JSON object we asked for: {reply!r}") from error
    if not isinstance(record, dict):
        raise ValueError(f"reply is not a JSON object: {reply!r}")
    return {str(key).lower(): value for key, value in record.items()}


def parse_reply(reply, config):
    """The four-field object behind a reply, in whichever shape we asked for."""
    if config.get("output_format", "json") == "lines":
        record = read_lines(reply)
    else:
        record = read_json(reply)
    missing = [field for field in FIELDS if field not in record]
    if missing:
        raise ValueError(f"reply leaves out {', '.join(missing)}: {reply!r}")
    tenant = str(record["tenant"]).strip()
    if not tenant:
        raise ValueError(f"reply names no tenant: {reply!r}")
    renewal = str(record["renewal"]).strip().lower()
    if renewal not in RENEWAL_TYPES:
        raise ValueError(f"renewal {record['renewal']!r} is not one of {RENEWAL_TYPES}")
    return {
        "tenant": tenant,
        "term_months": read_integer("term_months", record["term_months"]),
        "notice_days": read_integer("notice_days", record["notice_days"]),
        "renewal": renewal,
    }


def read_integer(field, value):
    """A whole number of months or days, whichever way the model wrote it."""
    if isinstance(value, bool):
        raise ValueError(f"{field} is not a number: {value!r}")
    if isinstance(value, int):
        return value
    digits = str(value).strip()
    if not digits.isdigit():
        raise ValueError(f"{field} is not a whole number: {value!r}")
    return int(digits)


def call_model(model, prompt, temperature):
    """One completion from the provider, with the settings that reach the request."""
    from openai import OpenAI

    answer = OpenAI().chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return answer.choices[0].message.content


def run(input_text, config):
    model = config.get("model", "gpt-4o-mini")
    if model not in MODELS:
        raise ValueError("the model named in the settings is not one we have configured")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError("the temperature named in the settings is not one we have configured")
    return json.dumps(
        parse_reply(call_model(model, build_prompt(input_text, config), temperature), config)
    )
