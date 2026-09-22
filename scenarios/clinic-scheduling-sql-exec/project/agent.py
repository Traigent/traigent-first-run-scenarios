# SPDX-License-Identifier: Apache-2.0
"""Turns a front-desk question about the schedule into one SQLite query.

The scheduling team asks questions in plain words - who is double-booked on
Thursday, which rooms sat empty last month - and this module writes the query
that answers them against clinic.db. Four settings shape the call: which model
writes the query, whether the instruction asks for the query outright or for a
short plan first, how much of the schema is quoted into the prompt (the table
names, or the full DDL), and the sampling temperature. The schema text is
quoted here verbatim from schema.sql and checked against that file when the
module loads, so the two cannot drift apart unnoticed. The reply is unwrapped
from any code fence and returned as text. Nothing here runs the query; the
reporting script and the scorer do that, on their own terms.
"""

from pathlib import Path

from openai import OpenAI

MODELS = ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini")

PROMPT_STYLES = {
    "direct": "Write one SQLite SELECT statement that answers the question. Reply with the SQL only.",
    "planned": "First list the tables and columns the question needs, then write one SQLite SELECT statement that answers it. Put the final SQL in a ```sql code fence.",
}

SCHEMA_CONTEXT = {
    "table_list": "The database has these tables: patients, providers, rooms, procedures, appointments.",
    "full_ddl": """The database was created with this schema:
CREATE TABLE patients (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    city TEXT NOT NULL,
    insurance_plan TEXT NOT NULL,
    registered_on TEXT NOT NULL
);

CREATE TABLE providers (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    hired_on TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE rooms (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    floor INTEGER NOT NULL,
    room_type TEXT NOT NULL
);

CREATE TABLE procedures (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    base_fee REAL NOT NULL,
    room_type TEXT NOT NULL
);

CREATE TABLE appointments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    procedure_id INTEGER NOT NULL REFERENCES procedures(id),
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL,
    copay REAL NOT NULL,
    booked_on TEXT NOT NULL,
    booked_via TEXT NOT NULL
);""",
}

TEMPERATURES = (0.0, 0.7)

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
if SCHEMA_CONTEXT["full_ddl"] != (
    "The database was created with this schema:\n"
    + SCHEMA_FILE.read_text(encoding="utf-8").strip()
):
    raise RuntimeError("the schema quoted in SCHEMA_CONTEXT no longer matches schema.sql")


def build_prompt(question, config):
    """The request text, assembled from the two settings that shape its wording."""
    lines = [
        "You write SQLite queries for the front desk of a walk-in clinic.",
        PROMPT_STYLES[config.get("prompt_style", "direct")],
        SCHEMA_CONTEXT[config.get("schema_context", "full_ddl")],
        f"Question: {question}",
    ]
    return "\n\n".join(lines)


def strip_code_fence(reply):
    """The SQL inside the last code fence, or the whole reply when there is none."""
    text = reply.strip()
    if "```" not in text:
        return text
    blocks = text.split("```")
    # Fenced content sits at the odd positions; the last fence holds the final answer.
    fenced = [blocks[i] for i in range(1, len(blocks), 2)]
    if not fenced:
        return text
    body = fenced[-1]
    first_line, newline, rest = body.partition("\n")
    if newline and first_line.strip().lower() in ("sql", "sqlite", ""):
        body = rest
    return body.strip()


def call_model(model, prompt, temperature):
    """One completion from the model, at the sampling temperature asked for."""
    answer = OpenAI().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return answer.choices[0].message.content


def run(input_text, config):
    model = config.get("model", "gpt-4o-mini")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    return strip_code_fence(call_model(model, build_prompt(input_text, config), temperature))
