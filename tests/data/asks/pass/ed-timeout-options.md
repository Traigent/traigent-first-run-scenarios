<!-- ask-corpus
expect: pass
material: false
source: evaluation-and-dataset.md, When calibration runs long: ask once, one question carrying every option, lettered per SKILL.md
-->
Calibration ran past its budget, which says nothing about whether your evaluator works.

A. **Wait** (recommended) - re-run with a larger `--timeout`, sized for both phases.
B. **Take a named fix** - the per-call sleep at evaluator.py:12.
C. **Score it differently** - a deterministic match against the expected answer.
D. **Retry** - a stalled provider call looks the same from here.
E. **Build a new evaluation method** together.
