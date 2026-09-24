<!-- ask-corpus
expect: note
material: true
source: SKILL.md, Show readiness once: a Quality advisory "cite[s] representative rows" - rows that are questions, in a table, above the one ask
note: above the routes besides the one they answer
-->
**Quality advisory** - every example is easy:

| id | input | expected |
|---|---|---|
| singer-3 | How many singers do we have? | SELECT count(*) FROM singer |
| singer-9 | What is the average age of all singers? | SELECT avg(age) FROM singer |

> Your dataset is here and I can run on it - 9 rows scored, so a difference between configurations
> can come down to one lucky row. Two ways forward:
>
> A. **Add generated examples up to 28 rows in total (recommended)** - the size this walkthrough
> is built for, so the run has enough to compare on.
> B. Continue on the nine, and the report carries the one-lucky-row limit.
>
> Or reply `I have it` with a path if there are rows I did not find.
