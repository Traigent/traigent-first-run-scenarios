"""The ask-shape grader, over a corpus of asks and as a script.

Every message the grader is held to lives in `tests/data/asks/`, one directory
per verdict: `pass/` must raise no finding and no note, `note/` must raise no
finding and print the note its header names, and `fail/` must raise the finding
its header names. Each entry cites its source: a guide file and section for a
guide rule, or "grader policy" where the verdict is this grader's own choice.
Expected verdicts follow the guide's rule, not the grader's behaviour. An ask
the guide prescribes is in `pass/` or `note/` where the guide puts it; the one
guide text in `fail/`, `copied-actor-on-material-ask.md`, is the guide's
copied-actor question graded as the one ask about material, a place the guide
does not put it and where its rule requires `I have it`. An ask the guide
forbids by a rule the grader cannot decide from the message's structure and
the guide's two tokens is in `note/`, never in `pass/`.

One test runs the grader over all of it, so a rule change has to pass the
whole corpus. When `GUIDE` names a traigent-first-run checkout, the last test
also holds the real guide: its SKILL.md states every rule, every verbatim entry
still appears in it, and every ask that component-creation.md, run-safety.md
and evaluation-and-dataset.md print in quoted, backticked or lettered form is
held verbatim in the corpus.

The script itself is run against a stand-in guide whose SKILL.md states the
rules in the guide's own sentences, wrapped the way the guide wraps them.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_ask_shape.py"
CORPUS = Path(__file__).resolve().parent / "data" / "asks"
sys.path.insert(0, str(SCRIPT.parent))

import check_ask_shape  # noqa: E402

SKILL = (
    "# Skill\n\n"
    "- Named routes are lettered from `A`, exactly one marked recommended, and\n"
    "  answerable by reply. No route carries a decision of its own. Keep the\n"
    "  question last; a route list is never compressed into yes/no. `I have it`\n"
    "  is unnumbered, last, and only on material questions.\n\n"
    "Always end with `I have it` and a path as an unnumbered\nalternative.\n"
)

ASK = (
    "Your rows are here, and the evaluator returns one score for every answer.\n"
    "\n"
    "- **A.** I build a working evaluator in a copy, then carry on\n"
    "  *(recommended - nothing of yours changes)*.\n"
    "- **B.** Pause, and I list the checks a corrected evaluator has to pass.\n"
    "\n"
    "Or reply `I have it` with a path, and I will use yours.\n"
)

HEADER = re.compile(r"\A<!-- ask-corpus\n(?P<fields>.*?)\n-->\n", re.DOTALL)
FIELDS = {"expect", "material", "source", "verbatim", "finding", "note"}
VERDICTS = ("pass", "note", "fail")
# The references whose printed asks the corpus must hold verbatim, and how many
# asks each prints at the pinned guide, so an extraction that stops finding them
# fails rather than passing on nothing.
REFERENCES = {
    "component-creation.md": 4,
    "run-safety.md": 5,
    "evaluation-and-dataset.md": 2,
}


def corpus() -> list[tuple[Path, dict[str, str], str]]:
    """Every corpus entry: its path, its header fields and the message."""
    entries = []
    for path in sorted(CORPUS.glob("*/*.md")):
        text = path.read_text(encoding="utf-8")
        header = HEADER.match(text)
        if header is None:
            raise AssertionError(f"{path} has no ask-corpus header")
        fields = dict(
            line.split(": ", 1) for line in header.group("fields").splitlines()
        )
        if not set(fields) <= FIELDS:
            raise AssertionError(f"{path}: unknown fields {set(fields) - FIELDS}")
        entries.append((path, fields, text[header.end() :]))
    return entries


def printed_asks(reference: str) -> list[str]:
    """Every ask a guide reference prints: a run of quoted lines that offers a
    route, a mark or `I have it`, or ends on a question; a backticked span
    offering lettered routes with the mark; and a block of lines lettered from
    `A.` (or `` `A.` ``) through `B.`."""
    asks = []
    runs: list[list[str]] = [[]]
    for line in reference.splitlines():
        if line.lstrip().startswith(">"):
            runs[-1].append(line)
        elif runs[-1]:
            runs.append([])
    for run in runs:
        block = "\n".join(run)
        if run and (
            check_ask_shape.STANDING.search(block)
            or check_ask_shape.MARKED.search(block)
            or re.search(r"^[ \t]*>[ \t]*(?:\*\*)?A\.", block, re.MULTILINE)
            or block.rstrip().endswith("?")
        ):
            asks.append(block)
    for span in re.finditer(r"`([^`]*)`", reference):
        inner = span.group(1)
        if re.search(r"(?:^|\. )A\. ", inner) and check_ask_shape.MARKED.search(inner):
            asks.append(inner)
    for block in re.finditer(
        r"^(?:A\. |- `A\.` )[^\n]*(?:\n[^\n]*\S[^\n]*)*", reference, re.MULTILINE
    ):
        if re.search(r"^(?:B\. |- `B\.` )", block.group(0), re.MULTILINE):
            asks.append(block.group(0))
    return asks


class CheckAskShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.guide = Path(self.temporary.name) / "guide"
        (self.guide / check_ask_shape.SKILL_PATH).parent.mkdir(parents=True)
        (self.guide / check_ask_shape.SKILL_PATH).write_text(SKILL, encoding="utf-8")

    def run_script(self, text: str, *arguments: str) -> tuple[int, str]:
        response = Path(self.temporary.name) / "response.md"
        response.write_text(text, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--guide", str(self.guide), *arguments]
            + [str(response)],
            capture_output=True,
            text=True,
        )
        return done.returncode, done.stdout + done.stderr

    def test_every_ask_in_the_corpus_gets_its_declared_verdict(self) -> None:
        entries = corpus()
        for path, fields, text in entries:
            with self.subTest(entry=f"{path.parent.name}/{path.name}"):
                self.assertEqual(path.parent.name, fields["expect"])
                self.assertIn(fields["expect"], VERDICTS)
                self.assertIn(fields["material"], ("true", "false"))
                self.assertTrue(fields["source"].strip())
                grade = check_ask_shape.check_ask_shape(
                    text, material=fields["material"] == "true"
                )
                if fields["expect"] == "fail":
                    self.assertNotIn("note", fields)
                    self.assertTrue(
                        any(fields["finding"] in item for item in grade.findings),
                        f"wanted {fields['finding']!r}, got {grade.findings}",
                    )
                    continue
                self.assertNotIn("finding", fields)
                self.assertEqual((), grade.findings)
                if fields["expect"] == "pass":
                    self.assertNotIn("note", fields)
                    self.assertEqual((), grade.notes)
                else:
                    self.assertTrue(
                        any(fields["note"] in item for item in grade.notes),
                        f"wanted note {fields['note']!r}, got {grade.notes}",
                    )
        kinds = [fields["expect"] for _, fields, _ in entries]
        self.assertGreaterEqual(kinds.count("pass"), 60)
        self.assertGreaterEqual(kinds.count("note"), 35)
        self.assertGreaterEqual(kinds.count("fail"), 20)

    def test_the_mark_is_counted_never_the_bare_word(self) -> None:
        """Two routes each carrying `(recommended)` fail; "(not recommended)"
        and "less recommended" beside one mark pass, and routes that only say
        recommended in other words are noted, not failed."""
        marked = ASK.replace("pass.", "pass (recommended).")
        self.assertIn(
            "2 of the 2 routes carry the `(recommended)` mark",
            " ".join(check_ask_shape.check_ask_shape(marked, material=True).findings),
        )
        for text in (
            ASK.replace("pass.", "pass (not recommended)."),
            ASK.replace("pass.", "pass - less recommended."),
        ):
            with self.subTest(text=text):
                grade = check_ask_shape.check_ask_shape(text, material=True)
                self.assertEqual((), grade.findings)
        prose = ASK.replace(
            "*(recommended - nothing of yours changes)*", "which is recommended"
        )
        grade = check_ask_shape.check_ask_shape(prose, material=True)
        self.assertEqual((), grade.findings)
        self.assertIn(
            "no route carries the `(recommended)` mark", " ".join(grade.notes)
        )

    def test_a_well_shaped_ask_passes_however_it_was_captured(self) -> None:
        for label, text in (
            ("as written", ASK),
            ("quoted", "".join(f"> {line}\n" for line in ASK.splitlines())),
            (
                "standing line right under the routes",
                ASK.replace("pass.\n\n", "pass.\n"),
            ),
        ):
            with self.subTest(label=label):
                status, output = self.run_script(text, "--material")
                self.assertEqual(0, status, output)
                self.assertIn("ASK SHAPE: OK", output)
                self.assertNotIn("note:", output)

    def test_a_misshapen_ask_fails_with_every_finding(self) -> None:
        text = ASK.replace("**B.**", "**C.**").replace("Or reply", "- **D.**")
        status, output = self.run_script(text, "--material")
        self.assertEqual(1, status, output)
        self.assertIn("- options are labelled A, C, D", output)
        self.assertIn("- route D opens on `I have it`", output)
        # One miss, one finding: `I have it` is there, in a route.
        self.assertNotIn("does not end on", output)
        self.assertIn("ASK SHAPE: FAIL", output)

    def test_notes_are_printed_and_never_fail(self) -> None:
        text = ASK + "\nShould I add rows as well?\n"
        status, output = self.run_script(text, "--material")
        self.assertEqual(0, status, output)
        self.assertIn("note: a question follows `I have it`", output)
        self.assertIn("ASK SHAPE: OK", output)

    def test_i_have_it_is_required_only_on_an_ask_about_material(self) -> None:
        without = ASK.split("\nOr reply")[0]
        self.assertEqual(0, self.run_script(without)[0])
        self.assertEqual(1, self.run_script(without, "--material")[0])

    def test_a_guide_that_no_longer_states_a_rule_is_not_graded(self) -> None:
        for rule in check_ask_shape.RULES:
            with self.subTest(rule=rule):
                stated = " ".join(SKILL.split())
                (self.guide / check_ask_shape.SKILL_PATH).write_text(
                    stated.replace(" ".join(rule.split()), "", 1), encoding="utf-8"
                )
                status, output = self.run_script(ASK)
                self.assertEqual(2, status, output)
                self.assertIn("no longer states", output)
        (self.guide / check_ask_shape.SKILL_PATH).unlink()
        status, output = self.run_script(ASK)
        self.assertEqual(2, status)
        self.assertIn("COULD NOT GRADE", output)

    @unittest.skipUnless(os.environ.get("GUIDE"), "set GUIDE to a guide checkout")
    def test_the_guide_states_every_rule_and_the_corpus_holds_its_asks(self) -> None:
        guide = Path(os.environ["GUIDE"])
        skill = (guide / check_ask_shape.SKILL_PATH).read_text(encoding="utf-8")
        self.assertEqual([], check_ask_shape.missing_rules(skill))
        verbatim = []
        for path, fields, text in corpus():
            if "verbatim" in fields:
                with self.subTest(entry=path.name):
                    source = (guide / fields["verbatim"]).read_text(encoding="utf-8")
                    self.assertIn(text.rstrip("\n"), source)
                    verbatim.append(text)
        self.assertGreaterEqual(len(verbatim), 11)
        references = guide / "skills" / "traigent-first-run" / "references"
        for name, count in REFERENCES.items():
            asks = printed_asks((references / name).read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(asks), count, f"the asks {name} prints")
            for ask in asks:
                with self.subTest(reference=name, ask=ask[:60]):
                    self.assertTrue(
                        any(ask.strip() in text for text in verbatim),
                        f"{name} prints an ask the corpus does not hold verbatim",
                    )


if __name__ == "__main__":
    unittest.main()
