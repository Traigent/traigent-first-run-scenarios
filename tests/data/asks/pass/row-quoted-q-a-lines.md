<!-- ask-corpus
expect: pass
material: true
source: grader policy: a list starting elsewhere than `A` and marking nothing is not read as routes - a row quoted as Q:/A: lines above the ask
-->
One row I read:

Q: which rooms are on the second floor
A: SELECT name FROM rooms WHERE floor = 2

> Your dataset is here and I can run on it - 9 rows scored, so a difference between configurations
> can come down to one lucky row. Two ways forward:
>
> A. **Add generated examples up to 28 rows in total (recommended)** - the size this walkthrough
> is built for, so the run has enough to compare on.
> B. Continue on the nine, and the report carries the one-lucky-row limit.
>
> Or reply `I have it` with a path if there are rows I did not find.
