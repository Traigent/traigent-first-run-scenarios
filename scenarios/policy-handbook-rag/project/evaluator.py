# SPDX-License-Identifier: Apache-2.0
"""Compares a handbook answer with the one the People team recorded.

Every question in our set has one short recorded answer -- a number, a name,
a phrase or yes/no -- and the People team also listed the other spellings
they would accept, such as "16 weeks" beside "sixteen weeks" or "the IT
Service Desk" beside "IT Service Desk". An answer is right when, after
normalising, it equals the recorded answer or one of those spellings, and
wrong otherwise. Normalising folds case, drops punctuation and the articles
"a", "an" and "the", and collapses whitespace, so "The IT service desk." and
"IT Service Desk" are the same answer; it does not attempt anything cleverer,
because a reply that hedges or adds a second answer should score as wrong.

The accepted spellings travel with each row under metadata.aliases. A row
whose recorded answer is missing cannot be graded against, so it is raised
rather than scored, because scoring it 0.0 would quietly mark every reply
wrong.
"""

import re

ARTICLES = frozenset({"a", "an", "the"})

WORD_PATTERN = re.compile(r"[a-z0-9]+")


def normalise(text):
    """The comparable form of an answer: case, punctuation and articles removed."""
    words = WORD_PATTERN.findall(str(text).casefold().replace("£", " "))
    return " ".join(word for word in words if word not in ARTICLES)


def accepted_answers(expected, metadata):
    """The recorded answer and every spelling the People team listed beside it."""
    aliases = []
    if isinstance(metadata, dict):
        aliases = metadata.get("aliases")
        if aliases is None and isinstance(metadata.get("metadata"), dict):
            aliases = metadata["metadata"].get("aliases")
    if aliases is None:
        aliases = []
    if not isinstance(aliases, (list, tuple)):
        raise ValueError(f"metadata.aliases must be a list of strings, not {aliases!r}")
    return [expected, *aliases]


def score(output, expected, input_data=None, metadata=None):
    if not isinstance(expected, str) or not expected.strip():
        raise ValueError(
            f"recorded answer {expected!r} is empty -- the row cannot be graded against"
        )
    accepted = {normalise(answer) for answer in accepted_answers(expected, metadata)}
    accepted.discard("")
    if not accepted:
        raise ValueError(
            f"recorded answer {expected!r} normalises to nothing -- the row cannot be graded against"
        )
    return 1.0 if normalise(output) in accepted else 0.0
