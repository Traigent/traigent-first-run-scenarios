<!-- ask-corpus
expect: pass
material: true
source: SKILL.md, Quality advisory, bulleted, with evaluation-and-dataset.md's finding format ("Recommended: repair a working copy and re-run validation."), folded into the one ask (component-creation.md, The gap-question contract)
-->
**Quality advisory**

- ❗ Evaluator - compares SQL as text; `SELECT a, b` and `SELECT b, a` score differently.
- Why it matters: optimization rewards the wrong behavior.
- Recommended: repair a working copy and re-run validation.

> Your dataset is here and I can run on it - 9 rows scored, so a difference between configurations
> can come down to one lucky row. Two ways forward:
>
> A. **Add generated examples up to 28 rows in total (recommended)** - the size this walkthrough
> is built for, so the run has enough to compare on. Your own rows stay exactly as they are; the
> rows I add are declared as written for this walkthrough and are weaker evidence than your own, so
> this first run reads as a walkthrough of the workflow, not a measurement of your product.
> B. Continue on the nine, and the report carries the one-lucky-row limit.
>
> Or reply `I have it` with a path if there are rows I did not find.
