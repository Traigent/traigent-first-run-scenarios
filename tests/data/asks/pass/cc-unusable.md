<!-- ask-corpus
expect: pass
material: true
source: component-creation.md, When a component is present but unusable: the worked ask, verbatim
verbatim: skills/traigent-first-run/references/component-creation.md
-->
> Your dataset is real and I can run on it. The agent here echoes its input back rather than
> attempting what your rows describe, and the evaluator it would be graded by returns the same
> score for every answer, so nothing can be graded yet. Two ways forward:
>
> A. **I build both (recommended).** In a reversible copy under `traigent-runs/`, leaving yours
> untouched, and re-validate, then carry on. Neither file has anything to mend - no call path in
> one, no rubric in the other - so what I write is a generated stand-in: not a repair
> of yours, a substitute for it. The run then measures my stand-ins against the selected rows from your 30 and your
> task, so it shows the workflow end to end and cannot tell you how your own code performs.
> B. Pause, and I will give you the exact checks a corrected version has to pass. Fix them and the
> same first run measures your code instead of my stand-ins.
>
> Either way this first run is a bounded one - a small sample and a capped number of trials, priced
> before it starts. It is a taste of the workflow, not a full search.
>
> Or reply `I have it` with a path - `agent: <path>`, `dataset: <path>`, `evaluation: <path>` - and
> I will use yours instead. I keep the agent I selected unless you point me elsewhere.
