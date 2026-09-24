# SPDX-License-Identifier: Apache-2.0
"""Grade the shape of the ask a first-run worker stopped on.

A readiness payload can match its contract while the message the customer reads
asks badly: the standing `I have it` exit lettered as a route, two routes marked
recommended, options numbered instead of lettered. This grades that message
against the rules the guide states for every ask.

The rules are the guide's, and they are read from the guide at run time. The
checks below implement these sentences of `skills/traigent-first-run/SKILL.md`,
and a guide that no longer states one of them is refused rather than graded
against a rule it has dropped: "Named routes are lettered from `A`, exactly one
marked recommended, and answerable by reply."; "No route carries a decision of
its own."; "Keep the question last; a route list is never compressed into
yes/no."; "`I have it` is unnumbered, last, and only on material questions.";
and "Always end with `I have it` and a path as an unnumbered alternative."

There are two tiers, and one principle divides them: a finding - which fails
the grade - may turn only on the message's structure - its labels, in the forms
listed below, its blank lines and how far its lines are indented - and on the
two literal tokens the guide defines for an ask, the mark `(recommended` and
`I have it`, in the spellings listed below. Beyond those forms and spellings a
word may hold a finding back as a note but never raise one, and a route's text
never ends where a sentence does. Whatever needs a word to be recognised -
whether a sentence is a second question or a customer's row quoted back,
whether "I recommend" is a recommendation, whether `I have it` inside a route
is the standing line or a path inside the choices - is a note, printed for a
person and never failing. The one exception is the grader's own fail-closed
policy on a message it cannot read as an ask at all.

What a route is. A label line opens - in a list item, a heading, a table row or
an ordered-list item ("1. **A.** ..."), bare, in bold or in backticks - on a
label: `A.`, `A)`, `A:`, `A -`, `(A)` or `Option A:`, where the label is a
letter, a number or a roman numeral followed by a space, so `e.g.` is not one.
Its shape is that prefix: a frame - table cell, heading level, `(A)` or
`Option A` form, and separator - and an emphasis - bullet, list number, bold
and backticks. A label that is the first of a sequence (`A`, `1`, `i`) starts a
list. Any other label line joins the list above it: in that list's shape,
across blank lines, and across other text when its label comes later in the
same sequence; in the same frame with another emphasis, when its label is of
the list's sequence (capitals, lower case, numbers or roman numerals) and its
line comes directly under the list's last label line or across blank lines
only. It never joins a list whose last label it comes more than three after in
the same sequence: the guide offers at most three choices on one question
(component-creation.md, "When nothing anchors task intent"), so no route list
jumps further, and quoted `Q:`/`A:` rows are not routes however many there are.
A line that joins nothing and does not start a sequence stands alone, and the
list above it stays open to the line after it - unless the lone line's label
comes between the two, when it is the route written in another form. The lines
after such a route are then not graded with the list above it: a gap, either
mark rule, a route opening on the standing line and `I have it` offered above
the last route go unfound after it, and the note on that route is what prompts
a person to read them. So `### A.`, a prose line opening `B.`, `### C.` reads
as routes A and C apart, with B noted, not as a gap. A list is read as routes
when it has two or more labels starting at `A`, or when a route in it carries
the mark, a single label line only where its label starts a sequence; a list
starting elsewhere and unmarked (files numbered 1 and 2), a single label line
that does not start a sequence, and options in another shape (keycaps, bullets,
bold words) are not. The last list read as routes is the ask's routes. Routes
on one line count too: in a paragraph with fewer than two label lines, a
capital and a full stop after sentence ends that run A, B, C in order, the form
of the guide's inline asks. A capital that does not continue the run is left
out of it and noted.

A route's text runs from its label to the next label, the end of its
paragraph, or the start of a later line of that paragraph that is indented no
deeper than the label's line and opens on the standing line - `I have it`, or
"reply" and it, behind nothing but punctuation and the guide's own "Or", as in
"Or reply `I have it` with a path". A sentence never ends it. A route's reach, where its mark is looked for, runs to
the next route of its list. The last route's reach is its paragraph; the
paragraph after it too when its label's line is the whole of its paragraph, as
a heading's or a bold title's is; then each paragraph after that indented
deeper than its label's line. It stops at the next label and at the first
`I have it` after its label.

Graded - each a finding that fails, with what it turns on:

- the message is empty (no character but whitespace);
- a list read as routes whose labels do not run A, B, C from `A` - numbered,
  roman or lower-case labels on a marked list, a gap, or a repeat other than
  of `A` (labels);
- two or more of the routes carrying the mark in their reach, or none of them
  carrying it in a message that never says "recommend" in any form, where no
  route can be marked (labels, reach and the mark; the word only holds the
  second back). "(not recommended)" and "less recommended" are not the mark;
- a route whose text opens on the standing line, the standing exit lettered
  as a route: "C. `I have it` - give me a path", "C. Or reply `I have it` with
  a path" (labels and the token, "reply" and "Or" before it);
- `I have it` offered only above the last route's label, counting every one
  inside a route or not, but none inside a route that opens on the standing
  line (labels and the token);
- on an ask about material, no "I have it" anywhere (the token, absent).
  Whether an ask is about material is the caller's statement (`--material`);
- and, as grader policy rather than a guide rule: no route, no `?`, no mark,
  no form of "recommend", no reply to give (`Reply` and a backticked answer)
  and no "I have it" - an ask this grader cannot read is not a pass.

A miss raises one finding: a route that opens on the standing line is that
finding alone, never also "offered before the last route" or "does not end on
`I have it`".

`I have it` counts in backticks, in bold, or after "reply" in any case, bare or
in straight or curly quotes, so a route saying "I have it drafted" is prose;
and a text that opens on it, "reply" and it, or "Or" and either, opens on the
standing line.

Noted - printed as notes, never failing:

- a question or decision phrase above the routes other than the one they
  answer: the first question in the paragraph that leads into them is theirs,
  and a question beside the default the gap question's objective line states
  in the guide's words ("accuracy, with cost when measurable") is that line;
  quoted text on a row cited in the guide's shape (a bullet opening on its id,
  then its input) is skipped;
- a question or decision phrase inside a route, or between the routes and
  `I have it`. A decision phrase is "tell me", "say", "let me know", "decide",
  "choose", "pick" or "confirm" followed by whether, which or if, as an
  imperative;
- `I have it` inside a route's text anywhere but at its opening - a later
  sentence, a continuation line, a reply line, or a line under the route that
  opens on something else ("If you have one, reply `I have it`") - and a route
  opening on "I have it" in another spelling: whether it is the standing line
  or a path inside the choices takes reading;
- a `(recommended)` mark outside every route's reach, and a bullet that
  recommends an option ("- Build it - recommended");
- no route carrying the mark in a message that recommends in words, and a
  second route that also says recommended beside the one marked;
- an earlier list that recommends a route, marked or in words;
- lines labelled in a list not read as routes, in a message that asks or
  recommends something;
- a label line that does not join the list above it only because its frame
  differs, where its label comes later in that list's sequence, at most three
  on, and that list is read as routes or starts at `A` ("route B is written in
  another form from route A above it"); and, wherever it sits, the route in
  another form whose label comes between a capital-lettered list and the line
  after it that would otherwise have joined that list, which is why nothing
  after it is graded;
- a label line of a list's frame and sequence kept out of a list that starts at
  `A` only because it comes more than three after its last label ("label E
  comes more than 3 after label A above it");
- a capital and a full stop that does not continue the run of inline routes;
- "I have it" only in another spelling, on an ask about material;
- `I have it` offered more than once, and a question, a decision phrase
  (its own sentence included), "while you decide" or another paragraph after
  it ("text follows the `I have it` paragraph");
- a yes/no question on an ask with no route list: whether routes were owed and
  compressed into it depends on the run, and the guide's own offer (component-
  creation.md, "Wording the offer") is a single yes/no proposal.

Not graded, and not noted:

- text inside a closed code fence, where a worker quotes the readiness card; an
  unclosed fence is graded like any other text, its label lines included;
- a label that is not at the start of a line or of a sentence ("plan A"), a
  single label line unless it starts a sequence and carries the mark, and a
  label line in a shape or sequence of its own, such as an `A.` after the
  routes, a label in another frame that repeats or precedes one of the list's
  own, or one in another emphasis with text between it and the list's last
  label line;
- two shapes the other-form note leaves quiet: an unmarked lower-case list split
  by form (`a.` then `b)`, whatever follows), since that note is kept for lists
  read as routes or starting at `A`; and a label in another form more than
  three past a list's last (`A.`, `B.`, then `F)`), which neither that note nor
  the ceiling note, kept for a list's own form, covers;
- a second question put as the first question of the paragraph that leads into
  the routes, or beside the objective line's default, and quoted text on a
  cited row: each is taken for what it is shaped as;
- a recommendation spelled other than `(recommended...)` outside the routes and
  bullets, and a second decision asked in words other than the ones above;
- a `?` inside a URL;
- whether `I have it` is absent where the question is not about material;
- and, because each needs the run's context rather than the message's shape:
  that a route does what it says, that the ask is the right one, and that it
  sits below the result it follows.

The messages it is held to live in `tests/data/asks/`: `pass/` must pass with no
note, `note/` must pass and print the note it names, and `fail/` must fail with
the finding it names. A pass is a precondition for a good ask, not evidence of
one.

    python scripts/check_ask_shape.py --guide ../traigent-first-run response.md

Exit 0 when no finding is raised (notes are printed either way), 1 with
findings, 2 when the guide or the message cannot be read or the guide no longer
states a rule this script implements.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

SKILL_PATH = Path("skills") / "traigent-first-run" / "SKILL.md"

# The sentences the checks implement, exactly as SKILL.md states them. Matched
# with runs of whitespace collapsed, because the guide wraps its lines.
RULES = (
    "Named routes are lettered from `A`, exactly one marked recommended, and "
    "answerable by reply.",
    "No route carries a decision of its own.",
    "Keep the question last; a route list is never compressed into yes/no.",
    "`I have it` is unnumbered, last, and only on material questions.",
    "Always end with `I have it` and a path as an unnumbered alternative.",
)

# A label: a capital or lower-case letter, a number, or a roman numeral. A bare
# `I` counts only before `.` or `)`, so a line opening "I - " or "I: " is prose.
LABEL = r"[A-HJ-Za-z]|[0-9]{1,2}|[ivxlc]{2,5}|(?:II|III|IV|VI|VII|VIII|IX)"
SEPARATOR = r"[.):|\-\u2013\u2014]"
# A label line: an optional table cell, heading, bullet, list number (only
# before a letter label, as in "1. **A.** ..."), bold and backtick, then `(A)`,
# `Option A:` or a bare label and its separator, then a space and text. The
# space rules out `e.g.` and `i.e.`. The prefix is the line's shape: labels in
# one list share it.
OPTION = re.compile(
    r"^[ \t]*(?P<table>\|[ \t]*)?(?P<heading>#{1,6}[ \t]+)?"
    r"(?P<bullet>[-*+\u2022][ \t]+)?"
    r"(?P<number>[0-9]{1,2}[.)][ \t]+(?=(?:\*\*)?`?(?:[A-Z]`?(?:\*\*)?[.)]|\([A-Z]\))))?"
    r"(?P<bold>\*\*)?(?P<tick>`)?"
    rf"(?:\((?P<paren>{LABEL})\)"
    rf"|(?:[Oo]ption|[Rr]oute|[Cc]hoice)[ \t]+(?P<named>{LABEL})"
    rf"(?=`?(?:\*\*)?[ \t]*{SEPARATOR})"
    rf"|(?P<bare>I(?=`?(?:\*\*)?[.)])|{LABEL})(?=`?(?:\*\*)?[ \t]*{SEPARATOR}))"
    rf"`?(?:\*\*)?[ \t]*(?P<separator>{SEPARATOR})?`?(?:\*\*)?(?=[ \t])[ \t]*(?=\S)",
    re.MULTILINE,
)
# An inline route: a capital and a full stop, at the start of a line or after a
# sentence end, as in "... uses. A. This run copies ... B. Paste ...".
INLINE = re.compile(r"(?:^|(?<=[.!?:;)] ))(?P<label>[A-Z])\.[ \t]+(?=\S)", re.MULTILINE)
# The standing line as the guide writes it - `I have it` in backticks - and as
# a worker commonly renders it: in bold, or after "reply" in any case, bare or
# in straight or curly quotes. "I have it" itself is case-sensitive, so prose
# that happens to say "i have it" is prose.
STANDING = re.compile(
    r"`I have it`|\*\*I have it\*\*|\b(?i:reply)[ \t]+[\"'\u201c\u2018]?I have it\b"
)
# "I have it" in any other spelling ("tell me \"I have it\""). Whether it is
# the standing line takes reading, so where it is the only one, that is a note.
PLAIN_STANDING = re.compile(r"\bI have it\b")
# An answer the customer is told to reply with: "Reply `continue`". It makes a
# message an ask for the fail-closed check; it is never a route of its own.
REPLY_ASK = re.compile(r"\b(?i:reply)\b[^\n]*?`[^`\n]+`")
# Text that opens on the standing line: the token, or "reply" and the token,
# behind nothing but punctuation and the guide's own "Or", as in "Or reply
# `I have it` with a path" or "C. `I have it` - give me a path". A route whose
# text opens so is the standing exit lettered as a route; a line below a route
# that opens so is not the route's text.
STANDING_LINE = re.compile(
    r"[^\w\n]*(?i:or[ \t]+)?(?:(?i:reply)[ \t]+[\"'\u201c\u2018]?I have it\b"
    r"|(?:(?i:reply)[ \t]+)?(?:`I have it`|\*\*I have it\*\*))"
)
# A route opening on "I have it" in another spelling: whether it is the
# standing exit or prose ("I have it drafted") takes reading.
PROMOTED_PLAIN = re.compile(r"[^\w\n]*I have it\b")
# Any form of "recommend": "recommended", "I recommend", "my recommendation".
RECOMMENDED = re.compile(r"\brecommend(?:ed|s|ing|ation)?\b", re.IGNORECASE)
# The mark as a route carries it, in parentheses: "(recommended)" or
# "(recommended - reason)". "(not recommended)" is not the mark.
MARKED = re.compile(r"\([ \t*_]*recommended\b", re.IGNORECASE)
# A second decision in words rather than a `?`. The guide's component reference
# names two as a route carrying a decision of its own - "tell me whether to
# redraw the split" and "say which you would prefer" - and "let me know",
# "decide", "choose", "pick" and "confirm" are the common spellings of the same
# ask. It counts only as an imperative put to the customer: at the start of the
# text or of a clause, or after "and", "or", "just", "please", "also" or "you".
DECISION = re.compile(
    r"(?:\A[ \t*_]*|[.;:!?,(][ \t*_]+|[-\u2013\u2014][ \t]+"
    r"|\b(?:and|or|just|please|also|you)\s+)"
    r"(?P<phrase>(?:tell\s+me|say|let\s+me\s+know|decide|choose|pick|confirm)\s+"
    r"(?:whether|which|if))\b",
    re.IGNORECASE,
)
# "While you decide" after the standing line is named by the guide as a second
# decision (component-creation.md: nothing follows it, "not a 'while you
# decide'").
WHILE_YOU_DECIDE = re.compile(r"\bwhile\s+you\s+decide\b", re.IGNORECASE)
# The default the gap question's item 5 states "in those words" when the
# customer names no objective (component-creation.md, "The gap-question
# contract"). A question beside it is that item, carried on the one question.
OBJECTIVE_DEFAULT = re.compile(
    r"accuracy,\s+with\s+cost\s+when\s+measurable", re.IGNORECASE
)
# A row cited the way the guide cites one ("A `no` is never a silent edit"):
# a bullet opening on the row's id in backticks, then its input. Quoted text on
# such an item is the row's, not the worker's, so a `?` there is not a question.
CITED_ROW = re.compile(
    r"^[ \t]*[-*+\u2022][ \t]+`[^`\n]+`[ \t]+[-\u2013\u2014][ \t]+input:",
    re.MULTILINE | re.IGNORECASE,
)
# A yes/no question: a sentence opening on an auxiliary verb and ending on `?`.
YES_NO = re.compile(
    r"(?:^|(?<=[.!?:] ))[ \t*_\"\u201c]*"
    r"(?:Shall|Should|Can|Could|May|Do|Does|Did|Will|Would|Is|Are)\b[^.!?\n]*\?",
    re.MULTILINE,
)
# A bullet whose text recommends in a mark-like spelling: "- Build it -
# recommended", "- Build it [recommended]", "- **Recommended:** build it".
BULLET_MARK = re.compile(
    r"^[ \t]*[-*+\u2022][ \t]+(?:[^\n]*?[-\u2013\u2014\[(][ \t*_]*|\*\*)"
    r"(?P<mark>recommended\b)",
    re.MULTILINE | re.IGNORECASE,
)
ITEM_END = re.compile(r"\n(?![ \t]+(?![-*+\u2022][ \t])\S)")
QUOTED = re.compile(r"`[^`\n]*`|\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d")
PARAGRAPH_END = re.compile(r"\n[ \t]*\n")
# The indentation of a line, past any blank lines before it.
INDENT = re.compile(r"(?:[ \t]*\n)*([ \t]*)")
BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
FENCE = re.compile(
    r"^[ \t]*(```|~~~)[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL
)
URL = re.compile(r"https?://\S+")
ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
FIRST_LABELS = frozenset({"A", "a", "1", "i", "I"})
# The most choices the guide offers on one question: "Offer at most three
# short choices" (component-creation.md, "When nothing anchors task intent"),
# "at most three short jobs" (SKILL.md, "Zero-anchor intent gate"); no ask it
# prints letters a route past `C`. A label more than this many past a list's
# last label cannot continue a list of routes, so it does not join one: a `Q:`
# row does not become route B of the `A:` row above it.
MOST_CHOICES = 3

Route = tuple[str, int, int, int]  # label, start, where its text begins, end
Start = tuple[str, int, int, tuple[object, ...]]  # label, start, body, shape


class Grade(NamedTuple):
    """What the grader found: findings fail the grade, notes are for a person."""

    findings: tuple[str, ...]
    notes: tuple[str, ...]


class GuideRuleMissing(Exception):
    """The guide no longer states a rule this script implements."""


def missing_rules(skill_text: str) -> list[str]:
    """The rule sentences the guide text does not state."""
    stated = " ".join(skill_text.split())
    return [rule for rule in RULES if " ".join(rule.split()) not in stated]


def _asks_something(text: str) -> bool:
    """Whether the text carries a question mark outside a URL."""
    return "?" in URL.sub("", text)


def _blank(text: str, start: int, end: int) -> str:
    """`text` with [start, end) replaced by spaces, newlines kept."""
    return text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]


def _questions(text: str) -> list[int]:
    """Where each question in `text` is: a run of `?` outside a URL, by its
    position, or a decision phrase, by its start."""
    for match in URL.finditer(text):
        text = _blank(text, match.start(), match.end())
    marks = [match.start() for match in re.finditer(r"\?+", text)]
    marks += [match.start("phrase") for match in DECISION.finditer(text)]
    return sorted(marks)


def _excerpt(text: str, position: int) -> str:
    """The sentence around `position`, on one line and at most 80 characters."""
    start = max(text.rfind(mark, 0, position) for mark in ".!?\n") + 1
    ends = [text.find(mark, position) for mark in ".!?\n"]
    end = min([index for index in ends if index != -1] or [len(text) - 1]) + 1
    sentence = " ".join(text[start:end].split())
    return sentence if len(sentence) <= 80 else sentence[:77] + "..."


def _quoted(text: str, positions: list[int]) -> str:
    return "; ".join(f'"{_excerpt(text, position)}"' for position in positions)


def _paragraphs(text: str) -> list[tuple[int, int]]:
    """The [start, end) of every paragraph of `text` that holds anything."""
    spans = []
    start = 0
    for match in [*PARAGRAPH_END.finditer(text), None]:
        end = match.start() if match else len(text)
        if text[start:end].strip():
            spans.append((start, end))
        start = match.end() if match else end
    return spans


def _ordinal(label: str) -> tuple[str, int]:
    """The sequence a label belongs to, and its place in it."""
    if label.isdigit():
        return "number", int(label)
    if len(label) > 1:
        values = [ROMAN[character] for character in label.lower()]
        return "roman", sum(
            -value if index + 1 < len(values) and values[index + 1] > value else value
            for index, value in enumerate(values)
        )
    if label.isupper():
        return "upper", ord(label) - ord("A")
    return "lower", ord(label) - ord("a")


def _later(earlier: str, label: str) -> bool:
    """Whether `label` comes after `earlier` in the same sequence."""
    (family, place), (other, later) = _ordinal(earlier), _ordinal(label)
    return family == other and later > place


def _indent(text: str, position: int) -> int:
    """The indentation of the line holding `position`, or of the first line
    after it that holds anything."""
    lead = INDENT.match(text, text.rfind("\n", 0, position) + 1)
    return len(lead.group(1).expandtabs(4)) if lead else 0


def _block_end(text: str, start: int, limit: int) -> int:
    """The end of the paragraph holding `start`, or `limit` if that is first."""
    paragraph = PARAGRAPH_END.search(text, start)
    return min(paragraph.start() if paragraph else len(text), limit)


def _route_end(text: str, start: int, limit: int) -> int:
    """Where the text of the route whose label starts at `start` ends: the end
    of its paragraph, `limit` (the next label), or the start of a later line of
    that paragraph that opens on the standing line, indented no deeper than the
    label's line, whichever comes first. A line indented deeper is the route's
    own continuation, and a sentence is never an end."""
    end = _block_end(text, start, limit)
    indent = _indent(text, start)
    line = text.find("\n", start, end)
    while line != -1:
        if _indent(text, line + 1) <= indent and STANDING_LINE.match(text, line + 1):
            return line + 1
        line = text.find("\n", line + 1, end)
    return end


def _joins(
    text: str,
    routes: list[Route],
    shape: tuple[object, ...],
    line: Start,
    *,
    ceiling: bool = True,
) -> bool:
    """Whether the label line `line` continues `routes`, a list in `shape`;
    with `ceiling` false, whether it would but for `MOST_CHOICES`."""
    label, start, _, own = line
    previous = routes[-1]
    (family, place), (other, later) = _ordinal(previous[0]), _ordinal(label)
    too_far = ceiling and family == other and later - place > MOST_CHOICES
    if label in FIRST_LABELS or too_far:
        return False
    if shape == own:
        gap = text[_block_end(text, previous[1], start) : start]
        return not gap.strip() or _later(previous[0], label)
    line_end = text.find("\n", previous[1], start)
    return (
        shape[:4] == own[:4]
        and family == other
        and line_end != -1
        and not text[line_end:start].strip()
    )


def _group(starts: list[Start], text: str) -> tuple[list[list[Route]], list[str]]:
    """Label lines grouped into the lists they form. A line whose label is the
    first of a sequence (`A`, `1`, `i`) starts a list. Any other joins the list
    above it in that list's shape across blank lines, and across other text
    when its label comes later in the same sequence. In a shape that differs
    only in emphasis - bold, backticks, a bullet or a list number, never the
    heading, table, `(A)` or `Option A` form or separator - it joins when its
    label is of the list's sequence (capitals, lower case, numbers or roman
    numerals) and its line comes directly under the list's last label line or
    across blank lines, so routes rendered with mixed emphasis, line under
    line, are graded as one list. No line joins a list whose last label it
    comes more than `MOST_CHOICES` after in the same sequence; one kept out
    only by that, from a list that starts at `A` as routes do, is noted. A
    line that joins nothing and does not start a sequence stands alone, and
    the list above it stays open to the line after it - unless the lone line's
    label comes between the two, when it is the route in another form, not a
    stray; then, where the line after it would have joined a list lettered in
    capitals, as routes are, that route is noted, since nothing after it is
    graded with the list."""
    lists: list[list[Route]] = []
    shapes: list[tuple[object, ...]] = []
    notes: list[str] = []
    for index, line in enumerate(starts):
        label, start, body, shape = line
        limit = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        route = (label, start, body, _route_end(text, start, limit))
        if lists and _joins(text, lists[-1], shapes[-1], line):
            lists[-1].append(route)
            continue
        above = -1
        if (
            len(lists) > 1
            and len(lists[-1]) == 1
            and lists[-1][0][0] not in FIRST_LABELS
        ):
            alone, last = lists[-1][0][0], lists[-2][-1][0]
            joins = _joins(text, lists[-2], shapes[-2], line)
            if not (_later(last, alone) and _later(alone, label)):
                above = -2
                if joins:
                    lists[-2].append(route)
                    lists.append(lists.pop(-2))
                    shapes.append(shapes.pop(-2))
                    continue
            elif joins and _ordinal(last)[0] == "upper":
                # The lone line is the route in another form, and it alone
                # keeps this line out of the list: say so, since nothing
                # after it is graded with the list above.
                notes.append(_other_form(alone, last))
        if (
            lists
            and lists[above][0][0] == "A"
            and _joins(text, lists[above], shapes[above], line, ceiling=False)
        ):
            notes.append(
                f"label {label} comes more than {MOST_CHOICES} after label "
                f"{lists[above][-1][0]} above it, in the same form, so it is not "
                "read with it - the guide offers at most three choices; read "
                "whether it is a route lettered out of order"
            )
        lists.append([route])
        shapes.append(shape)
    return lists, notes


def _shape(match: re.Match[str]) -> tuple[object, ...]:
    """A label line's shape: its frame - table cell, heading level, `(A)` or
    `Option A` form, and separator, any dash counted as one - then its
    emphasis: bullet, list number, bold and backticks."""
    return (
        bool(match.group("table")),
        (match.group("heading") or "").strip(),
        "paren" if match.group("paren") else "named" if match.group("named") else "",
        re.sub("[\u2013\u2014]", "-", match.group("separator") or ""),
        bool(match.group("bullet")),
        bool(match.group("number")),
        bool(match.group("bold")),
        bool(match.group("tick")),
    )


def _route_lists(text: str) -> tuple[list[list[Route]], list[str], list[str]]:
    """Every list of label lines, every inline run of routes, and the labels
    inline runs left out.

    An inline run is taken in a paragraph with fewer than two label lines,
    where a capital and a full stop after a sentence end runs A, B, C in
    order, at least one of them inside a line. A capital that does not
    continue the run ("Dr. B. Smith") is left out of it."""
    matches = list(OPTION.finditer(text))
    lines: list[Start] = [
        (
            match.group("paren") or match.group("named") or match.group("bare"),
            match.start(),
            match.end(),
            _shape(match),
        )
        for match in matches
    ]
    inline_lists = []
    skipped: list[str] = []
    for start, end in _paragraphs(text):
        if sum(1 for line in lines if start <= line[1] < end) > 1:
            continue
        run: list[tuple[str, int, int]] = []
        left_out: list[str] = []
        for match in INLINE.finditer(text, start, end):
            label = match.group("label")
            if (not run and label == "A") or (
                run and ord(label) == ord(run[-1][0]) + 1
            ):
                run.append((label, match.start(), match.end()))
            elif run or label != "A":
                left_out.append(_excerpt(text, match.start()))
        within = any(
            label_start > 0 and text[label_start - 1] != "\n"
            for _, label_start, _ in run
        )
        if run:
            skipped += left_out
        if len(run) > 1 and within:
            inline_lists.append(
                [
                    (
                        label,
                        label_start,
                        body,
                        _route_end(
                            text,
                            label_start,
                            run[index + 1][1] if index + 1 < len(run) else end,
                        ),
                    )
                    for index, (label, label_start, body) in enumerate(run)
                ]
            )
            lines = [line for line in lines if not start <= line[1] < end]
    grouped, far = _group(lines, text)
    lists = grouped + inline_lists
    return sorted(lists, key=lambda group: group[0][1]), skipped, far


def _other_frame(
    text: str, lists: list[list[Route]], graded: list[list[Route]]
) -> list[str]:
    """Notes on routes split apart by their frame: a list not read as routes
    whose first label does not start a sequence, whose line comes directly
    after the text of a route whose label line is in another frame, or across
    blank lines from it, where that route's list is read as routes or starts at
    `A`, as routes are lettered, and whose label comes later in that list's
    sequence, at most `MOST_CHOICES` on, without being one of its labels."""
    owners = {start: routes for routes in lists for _, start, _, _ in routes}
    notes = []
    for routes in lists:
        label, start, _, _ = routes[0]
        above = [position for position in owners if position < start]
        if routes in graded or label in FIRST_LABELS or not above:
            continue
        position = max(above)
        owner = owners[position]
        previous, end = next(
            (line[0], line[3]) for line in owner if line[1] == position
        )
        mine, theirs = OPTION.match(text, start), OPTION.match(text, position)
        if (
            mine is not None
            and theirs is not None
            and _shape(mine)[:4] != _shape(theirs)[:4]
            and not text[end:start].strip()
            and (owner in graded or owner[0][0] == "A")
            and _later(previous, label)
            and _ordinal(label)[1] - _ordinal(previous)[1] <= MOST_CHOICES
            and label not in [line[0] for line in owner]
        ):
            notes.append(_other_form(label, previous))
    return notes


def _other_form(label: str, previous: str) -> str:
    return (
        f"route {label} is written in another form from route {previous} above "
        "it, so the two are not graded as one list - read whether they are the "
        "routes of one ask"
    )


def _extent(text: str, start: int) -> int:
    """How far the last route's own text reaches: its paragraph; the paragraph
    after it too when the label's line is the whole of its paragraph, as a
    heading or a bold title is; and then each paragraph indented deeper than
    the label's line."""
    indent = _indent(text, start)
    paragraphs = [span for span in _paragraphs(text) if span[1] > start]
    opening, extent = paragraphs[0]
    rest = paragraphs[1:]
    line = text.rfind("\n", 0, start) + 1
    if (
        rest
        and not text[line:start].strip()
        and "\n" not in text[opening:extent].strip()
    ):
        extent = rest.pop(0)[1]
    for paragraph, end in rest:
        if _indent(text, paragraph) <= indent:
            break
        extent = end
    return extent


def _spans(routes: list[Route], text: str, stops: list[int]) -> list[tuple[int, int]]:
    """Each route's reach, for finding its mark: to the next route of its list,
    which takes in a paragraph explaining it; and for the last, its own text as
    `_extent` bounds it, up to the first `I have it` after its label or the
    next label line."""
    spans = [
        (start, routes[index + 1][1])
        for index, (_, start, _, _) in enumerate(routes[:-1])
    ]
    _, start, body, _ = routes[-1]
    reach = min([stop for stop in stops if stop > start] + [_extent(text, start)])
    standing = STANDING.search(text, body, reach)
    return spans + [(start, standing.start() if standing else reach)]


def _graded(routes: list[Route], text: str, stops: list[int]) -> bool:
    """A list read as routes: two or more labels from `A`, or one marked,
    where a single label line counts only when its label starts a sequence."""
    if len(routes) == 1 and routes[0][0] not in FIRST_LABELS:
        return False
    return (len(routes) > 1 and routes[0][0] == "A") or any(
        MARKED.search(text, start, end) for start, end in _spans(routes, text, stops)
    )


def check_ask_shape(text: str, *, material: bool) -> Grade:
    """The findings and notes for this message's ask."""
    text = BLOCKQUOTE.sub("", text)
    if not text.strip():
        return Grade(("the message is empty, so there is no ask to grade",), ())
    text = FENCE.sub(lambda match: "\n" * match.group(0).count("\n"), text)
    findings: list[str] = []
    notes: list[str] = []
    lists, skipped, far = _route_lists(text)
    stops = sorted(
        {match.start() for match in OPTION.finditer(text)}
        | {start for routes in lists for _, start, _, _ in routes}
    )
    graded = [routes for routes in lists if _graded(routes, text, stops)]
    for routes in graded:
        labels = [label for label, _, _, _ in routes]
        wanted = [chr(ord("A") + index) for index in range(len(routes))]
        if labels != wanted:
            findings.append(
                f"options are labelled {', '.join(labels)}; routes are lettered "
                f"{', '.join(wanted)}, from A, in order, with no gap and no repeat"
            )
        for label, _, body, end in routes:
            words = text[body:end]
            inside = STANDING.search(words) or PROMOTED_PLAIN.match(words)
            if STANDING_LINE.match(text, body):
                findings.append(
                    f"route {label} opens on `I have it`; it is never a route"
                )
            elif inside:
                notes.append(
                    f"route {label} offers `I have it` inside its text "
                    f'("{_excerpt(words, inside.start())}"); it is unnumbered and '
                    "last, never inside a route - read whether it is the standing "
                    "line or a path inside the choices"
                )
            questions = _questions(words)
            if questions:
                notes.append(
                    f"route {label} asks something of its own ({_quoted(words, questions)}); "
                    "no route carries a decision of its own - read whether it hands "
                    "the customer a second decision"
                )
    notes += far + [
        note for note in _other_frame(text, lists, graded) if note not in far
    ]
    if skipped:
        notes.append(
            "a capital and full stop that does not continue the run of inline "
            f"routes is not read as a route ({'; '.join(skipped)}); if it is one, "
            "routes are lettered A, B, C in order"
        )
    for routes in lists:
        if len(routes) > 1 and routes not in graded:
            asked = any(_questions(text[body:end]) for _, _, body, end in routes) or (
                not graded
                and (_asks_something(text) or RECOMMENDED.search(text) is not None)
            )
            if asked:
                named = ", ".join(label for label, _, _, _ in routes)
                notes.append(
                    f"lines labelled {named} are not read as routes, and the "
                    "message asks or recommends something; if they are options, "
                    "routes are lettered from A"
                )

    spans = [span for routes in graded for span in _spans(routes, text, stops)]
    outside = [
        match
        for match in MARKED.finditer(text)
        if not any(start <= match.start() < end for start, end in spans)
    ]
    if outside:
        notes.append(
            "a `(recommended)` mark sits outside every lettered route "
            f'("{_excerpt(text, outside[0].start())}"); routes are lettered from '
            "A and the mark goes on one of them - read whether it marks an option"
        )
    routes = graded[-1] if graded else []
    if any(
        RECOMMENDED.search(text, start, end)
        for earlier in graded[:-1]
        for start, end in _spans(earlier, text, stops)
    ):
        notes.append(
            "an earlier list also recommends a route; one ask means one "
            "decision in the whole message - read whether it is a second ask"
        )
    for match in BULLET_MARK.finditer(text):
        if not any(start <= match.start() < end for start, end in spans):
            notes.append(
                f'a bullet recommends an option ("{_excerpt(text, match.start("mark"))}"); '
                "routes are lettered from A - read whether these are options"
            )
            break
    if len(routes) > 1:
        notes += _marks(text, routes, _spans(routes, text, stops), findings)
        notes += _questions_above(text, routes, spans)

    bodies = [(start, end) for group in graded for _, start, _, end in group]
    promoted = [
        (start, end)
        for group in graded
        for _, start, body, end in group
        if STANDING_LINE.match(text, body)
    ]
    # Every `I have it` but a promoted route's own counts where it sits: above
    # the last route's label, it is offered too early, inside a route or not.
    offered = [
        match
        for match in STANDING.finditer(text)
        if not any(start <= match.start() < end for start, end in promoted)
    ]
    if routes and offered and offered[-1].start() < routes[-1][1]:
        findings.append("`I have it` is offered before the last route; it goes last")
    standing = [
        match
        for match in offered
        if not any(start <= match.start() < end for start, end in bodies)
    ]
    if len(routes) < 2:
        for match in YES_NO.finditer(text):
            notes.append(
                f'the ask is a yes/no question ("{_excerpt(text, match.end() - 1)}") '
                "with no lettered routes; a route list is never compressed into "
                "yes/no - read whether routes were owed"
            )
            break
    if not standing:
        # `I have it` inside a route is that route's finding or note, and in
        # another spelling it is a note: the finding below needs it absent
        # altogether, so one miss raises one finding.
        plain = PLAIN_STANDING.search(text)
        if material and plain and not STANDING.search(text):
            notes.append(
                f'"I have it" appears only in another spelling ("{_excerpt(text, plain.start())}"); '
                "the ask about material ends on `I have it` with a path - read "
                "whether this is it"
            )
        elif material and not plain:
            findings.append(
                "the ask is about material and does not end on `I have it` with a path"
            )
        elif not material and not (
            graded
            or _asks_something(text)
            or RECOMMENDED.search(text)
            or plain
            or REPLY_ASK.search(text)
        ):
            findings.append(
                "no ask was found - no route, no question, no recommendation, no "
                "reply to give and no `I have it` - and an ask this grader cannot "
                "read is not a pass"
            )
        return Grade(tuple(findings), tuple(notes))
    if len(standing) > 1:
        notes.append(
            f"`I have it` is offered {len(standing)} times; it is offered once"
        )
    last = standing[-1]
    if routes and last.start() < routes[-1][1]:
        # Offered too early (the finding above), or again inside the last
        # route (its note): what follows it is the routes themselves.
        return Grade(tuple(findings), tuple(notes))
    if routes:
        between = _questions(_blank(text, 0, routes[-1][3])[: last.start()])
        if between:
            notes.append(
                "the message asks something between its routes and `I have it` "
                f"({_quoted(text, between)}); one ask means one decision in the "
                "whole message - read whether it is a second ask"
            )
    notes += _after_standing(text, last)
    return Grade(tuple(findings), tuple(notes))


def _marks(
    text: str, routes: list[Route], reach: list[tuple[int, int]], findings: list[str]
) -> list[str]:
    """The mark count on the ask's routes. Two routes carrying the mark fail,
    and so does a message that never says "recommend" in any form, where no
    route can be marked. Anything short of that takes reading, so it is noted:
    no mark but a recommendation in words, and a second route that also says
    recommended beside the one marked."""
    marked = [
        index
        for index, (start, end) in enumerate(reach)
        if MARKED.search(text, start, end)
    ]
    if len(marked) > 1:
        findings.append(
            f"{len(marked)} of the {len(routes)} routes carry the "
            "`(recommended)` mark; exactly one is marked recommended"
        )
        return []
    if not marked:
        if RECOMMENDED.search(text):
            return [
                "no route carries the `(recommended)` mark, and the message "
                "recommends in other words; exactly one route is marked "
                "recommended - read which"
            ]
        findings.append(
            f"none of the {len(routes)} routes is marked recommended; exactly one is"
        )
        return []
    also = [
        routes[index][0]
        for index, (start, end) in enumerate(reach)
        if index != marked[0]
        and any(
            not re.search(
                r"\b(?:not|less|never)\s+$|\(\s*not\s+$",
                text[max(start, match.start() - 8) : match.start()],
                re.IGNORECASE,
            )
            for match in RECOMMENDED.finditer(text, start, end)
        )
    ]
    if also:
        return [
            f"route {', '.join(also)} also says recommended beside the one "
            "carrying the mark; exactly one is marked recommended - read whether "
            "it is a second mark"
        ]
    return []


def _after_standing(text: str, last: re.Match[str]) -> list[str]:
    """Notes on anything after the standing line, which closes the ask."""
    paragraph = PARAGRAPH_END.search(text, last.end())
    after = text[paragraph.end() :] if paragraph else ""
    # The standing line's own sentence may go on ("... if there are rows I did
    # not find"); a sentence after it may say what happens to the path.
    sentence = re.search(r"[.!?](?=\s|$)", text[last.end() :])
    later = text[last.end() + sentence.end() :] if sentence else ""
    decision = (
        DECISION.search(text[last.end() :])
        or DECISION.search(later)
        or WHILE_YOU_DECIDE.search(text, last.end())
    )
    if _asks_something(text[last.end() :]):
        position = last.end() + URL.sub(
            lambda match: " " * len(match.group(0)), text[last.end() :]
        ).index("?")
        return [
            f'a question follows `I have it` ("{_excerpt(text, position)}"); the '
            "ask ends on it - read whether it is a second ask"
        ]
    if decision:
        return [
            f'a decision phrase follows `I have it` ("{decision.group(0).strip()}"); '
            "the ask ends on it - read whether it is a second ask"
        ]
    if after.strip():
        return [
            "text follows the `I have it` paragraph; no customer-facing sentence "
            "follows it"
        ]
    return []


def _questions_above(
    text: str, routes: list[Route], spans: list[tuple[int, int]]
) -> list[str]:
    """A note on each question above the routes other than the one they answer.

    The paragraph that leads into the routes may carry the question they answer
    - "What should the walkthrough agent do?" (component-creation.md, "When
    nothing anchors task intent") - and the gap question's item 5 may ride on
    it anywhere above them, recognised by the default it states in the guide's
    words. Quoted text is skipped only on a row cited in the guide's shape.
    """
    above = text[: routes[0][1]]
    for start, end in spans:
        if start < len(above):
            above = _blank(above, start, min(end, len(above)))
    for row in CITED_ROW.finditer(above):
        item = ITEM_END.search(above, row.end())
        end = item.start() if item else len(above)
        for quote in QUOTED.finditer(above, row.start(), end):
            above = _blank(above, quote.start(), quote.end())
    paragraphs = _paragraphs(above)
    if not paragraphs:
        return []
    questions = _questions(above)
    for start, end in paragraphs:
        if OBJECTIVE_DEFAULT.search(above, start, end):
            first = next((mark for mark in questions if start <= mark < end), None)
            if first is not None:
                questions.remove(first)
            break
    lead_in = paragraphs[-1][0]
    theirs = next((mark for mark in questions if mark >= lead_in), None)
    extra = [mark for mark in questions if mark != theirs]
    if not extra:
        return []
    return [
        f"{len(extra)} question{'' if len(extra) == 1 else 's'} or decision "
        f"phrase{'' if len(extra) == 1 else 's'} above the routes besides the one "
        f"they answer ({_quoted(text, extra)}); one ask means one decision in the "
        "whole message - read whether each is quoted material or a second ask"
    ]


def read_guide_rules(guide: Path) -> None:
    """Refuse a guide that no longer states every rule graded here."""
    skill = guide / SKILL_PATH
    missing = missing_rules(skill.read_text(encoding="utf-8"))
    if missing:
        raise GuideRuleMissing(f"{skill} no longer states: " + " | ".join(missing))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grade the shape of the ask a first-run worker stopped on."
    )
    parser.add_argument("response", type=Path, help="the worker's final message")
    parser.add_argument(
        "--guide",
        type=Path,
        required=True,
        help="the traigent-first-run checkout the worker followed",
    )
    parser.add_argument(
        "--material",
        action="store_true",
        help="the ask is the one ask about missing or unusable material",
    )
    arguments = parser.parse_args(argv)
    try:
        read_guide_rules(arguments.guide)
        text = arguments.response.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, GuideRuleMissing) as exc:
        print(f"ASK SHAPE: COULD NOT GRADE ({exc})", file=sys.stderr)
        return 2
    grade = check_ask_shape(text, material=arguments.material)
    for finding in grade.findings:
        print(f"- {finding}")
    for note in grade.notes:
        print(f"note: {note}")
    print(f"ASK SHAPE: {'FAIL' if grade.findings else 'OK'}")
    return 1 if grade.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
