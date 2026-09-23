<!-- ask-corpus
expect: pass
material: false
source: evaluation-and-dataset.md, The row-level sanity check: "A `no` is never a silent edit", verbatim
verbatim: skills/traigent-first-run/references/evaluation-and-dataset.md
-->
> I suspect this dataset has rows that need fixing before the run.
>
> - `ticket-118` - input: *"Refund requested 45 days after purchase; the policy window is 30 days"*,
>   expected: `approve`. 45 days is outside the 30-day window the input itself states, so `approve`
>   contradicts it. **This row is in the 28 the run will use.**
> - `ticket-204` - ... (one line per row: the id, the quoted input and expected answer, the reason)
>
> I intend to fix the affected rows this first run will use - do you agree or disagree?
