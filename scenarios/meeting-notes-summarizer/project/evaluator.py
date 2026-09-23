# SPDX-License-Identifier: Apache-2.0
"""Scores a generated meeting summary against the one the note-taker wrote by hand.

The team's shared grader, in our notesqa package, scores against the rubric below: it reads the
candidate and the reference summary together and returns a number between 0 and 1 for how
completely the candidate covers the decisions and owners the reference names, and how much it
lets in that the reference left out. We use the same grader for every summarising job in the
company so the numbers are comparable across teams.
"""

RUBRIC = """\
A summary is graded on four points, in this order of importance.

1. Every decision the reference summary names is present, with the same outcome. A decision the
   meeting reversed counts only in its final form; reporting the abandoned version is an error.
2. Every follow-up is attributed to the same owner the reference names. A decision with the
   wrong owner, or no owner, is a partial miss.
3. Nothing is included that the reference left out: no small talk, no proposal that was raised
   and parked, no red herring the meeting explicitly rejected.
4. It is short, two or three sentences, and reads as a note a colleague would send.
"""


def score(output, expected, input_data=None, metadata=None):
    from notesqa.grading import SummaryGrader

    return SummaryGrader(rubric=RUBRIC).grade(output, expected)
