# SPDX-License-Identifier: Apache-2.0
"""Turns a stock question from the sales desk into one SQLite query over warehouse.db.

Four settings shape the call: which model writes the query, how much of the
schema it is shown (nothing, one line per table, or the full CREATE TABLE
text), which instruction wording leads the prompt, and the sampling
temperature. The schema is read from schema.sql next to this file so the two
never drift apart; the one-line-per-table form is cut from that same text.

The reply is returned as SQL text. Nothing here runs it: the desk tool that
calls run() decides whether and where the query executes, and this module only
strips a markdown code fence the model sometimes wraps around its answer.
"""

import re
from pathlib import Path

import litellm

MODELS = (
    "openrouter/openai/gpt-4o-mini",
    "openrouter/anthropic/claude-3.5-haiku",
    "openrouter/meta-llama/llama-3.3-70b-instruct",
)

SCHEMA_DDL = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")

TABLE_PATTERN = re.compile(r"CREATE TABLE (\w+) \((.*)\);", re.MULTILINE)
CONSTRAINT_WORDS = ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK")


def table_lines(ddl):
    """One line per table - its name and its column names, nothing else."""
    lines = []
    for table, body in TABLE_PATTERN.findall(ddl):
        # Split on the commas between column definitions, not the ones inside
        # a CHECK, REFERENCES or PRIMARY KEY parenthesis.
        parts = re.split(r",(?![^()]*\))", body)
        columns = [
            part.split()[0]
            for part in parts
            if part.split() and part.split()[0] not in CONSTRAINT_WORDS
        ]
        lines.append(f"{table}({', '.join(columns)})")
    return "\n".join(lines)


SCHEMA_CONTEXTS = {
    "none": "(not shown)",
    "table_lines": table_lines(SCHEMA_DDL),
    "full_ddl": SCHEMA_DDL,
}

PROMPT_STYLES = {
    "direct": "Write one SQLite SELECT statement that answers the question. Reply with the SQL only.",
    "reasoned": "Decide which tables and joins the question needs, then reply with one SQLite SELECT statement and nothing else.",
}

TEMPERATURES = (0.0, 0.7)

FENCE_PATTERN = re.compile(r"^\s*```(?:sql)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def build_prompt(question, config):
    """The request text: the instruction, the schema as the caller wants it shown, the question."""
    lines = [PROMPT_STYLES[config.get("prompt_style", "direct")]]
    schema_context = config.get("schema_context", "table_lines")
    if schema_context not in SCHEMA_CONTEXTS:
        raise ValueError(f"schema context {schema_context!r} is not one we render")
    lines.append(f"Schema:\n{SCHEMA_CONTEXTS[schema_context]}")
    lines.append(f"Question: {question}")
    return "\n\n".join(lines)


def strip_fence(reply):
    """The SQL inside a markdown code fence, or the reply as it came."""
    found = FENCE_PATTERN.match(reply)
    return (found.group(1) if found else reply).strip()


def call_model(model, prompt, temperature):
    """One completion from OpenRouter for this prompt."""
    reply = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return reply.choices[0].message.content


def run(input_text, config):
    model = config.get("model", "openrouter/openai/gpt-4o-mini")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    return strip_fence(call_model(model, build_prompt(input_text, config), temperature))
