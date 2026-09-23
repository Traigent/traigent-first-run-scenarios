# SPDX-License-Identifier: Apache-2.0
"""Answers a staff question from the Marrowfield Logistics handbook.

The handbook lives as markdown files under knowledge/. Each question is
matched against every paragraph by keyword overlap, the best few paragraphs
are placed in the prompt, and the model is asked for the answer alone -- a
number, a name, a short phrase, or yes/no -- so the reply can be compared with
the answer the People team recorded for that question.

Four settings shape the call: which model answers it, how the model is told
to read the retrieved passages, whether it answers directly or reasons first,
and the sampling temperature. Everything else is fixed.
"""

import re
from pathlib import Path

from anthropic import Anthropic

MODELS = ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6")

CONTEXT_FORMATS = {
    "quoted": "Treat each passage below as a verbatim quotation from the handbook file named above it, and answer only from its exact wording.",
    "bullets": "Read each passage below sentence by sentence, as a list of separate facts, and answer from the one fact that applies.",
    "raw": "Read the passages below as ordinary handbook paragraphs and answer from what they say.",
}

PROMPT_STYLES = {
    "direct": "Answer the question using only the handbook passages. Reply with the answer alone: a number, a name, a short phrase, or yes/no. Do not explain.",
    "reasoned": "Answer the question using only the handbook passages. First state in one sentence which rule applies, then give the answer by itself on the last line, prefixed with 'Answer:'.",
}

TEMPERATURES = (0.0, 0.5)

TOP_K = 4

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i if in is it its many "
    "may much must my not of on or our per should that the their there this to "
    "what when where which who whom will with you your".split()
)

WORD_PATTERN = re.compile(r"[a-z0-9]+")

ANSWER_PREFIX = re.compile(r"^\s*answer\s*:\s*", re.IGNORECASE)


def stem(word):
    """A word with its most common English ending removed, so claims matches claim."""
    for ending in ("ies", "ing", "ed", "es", "s"):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)] + ("y" if ending == "ies" else "")
    return word


def tokens(text):
    """The lower-case stemmed words of a text that carry meaning, as a set."""
    return {
        stem(word)
        for word in WORD_PATTERN.findall(text.lower())
        if word not in STOPWORDS
    }


def load_passages():
    """Every paragraph of every handbook file, with the file it came from."""
    passages = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for block in re.split(r"\n\s*\n", text):
            paragraph = " ".join(block.split())
            if paragraph and not paragraph.startswith("#"):
                passages.append((path.stem, paragraph))
    return passages


def retrieve(question):
    """The TOP_K paragraphs sharing the most words with the question."""
    asked = tokens(question)
    ranked = []
    for position, (source, paragraph) in enumerate(load_passages()):
        overlap = len(asked & tokens(paragraph))
        if overlap:
            ranked.append((-overlap, position, source, paragraph))
    ranked.sort()
    return [(source, paragraph) for _, _, source, paragraph in ranked[:TOP_K]]


def build_prompt(question, config):
    """The request text, assembled from the two settings that shape it."""
    lines = [
        PROMPT_STYLES[config.get("prompt_style", "direct")],
        CONTEXT_FORMATS[config.get("context_format", "quoted")],
    ]
    for source, paragraph in retrieve(question):
        lines.append(f"[{source}]\n{paragraph}")
    lines.append(f"Question: {question}")
    return "\n\n".join(lines)


def parse_reply(reply):
    """The short answer, read from the last line the model wrote."""
    answer = ""
    for line in str(reply).splitlines():
        if line.strip():
            answer = line.strip()
    answer = ANSWER_PREFIX.sub("", answer).strip().strip('"').strip()
    if not answer:
        raise ValueError(f"no answer in {reply!r}")
    return answer


def call_model(model, prompt, temperature):
    """One completion from the model, as the text it wrote."""
    answer = Anthropic().messages.create(
        model=model,
        max_tokens=200,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return answer.content[0].text


def run(input_text, config):
    model = config.get("model", "claude-sonnet-4-6")
    if model not in MODELS:
        raise ValueError(f"{model!r} is not one of the models we have configured")
    temperature = config.get("temperature", 0.0)
    if temperature not in TEMPERATURES:
        raise ValueError(f"temperature {temperature!r} is not one of {TEMPERATURES}")
    return parse_reply(call_model(model, build_prompt(input_text, config), temperature))
