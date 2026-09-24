<!-- ask-corpus
expect: pass
material: true
source: SKILL.md: the welcome is shown verbatim as the first run-facing message, and a zero-anchor run stops on its task question in that same turn (component-creation.md, When nothing anchors task intent); its numbered stages are not options
-->
> **Welcome to Traigent Onboarding!**
>
> 1. **Inspect** - preserve your agent, dataset, and evaluator.
> 2. **Readiness** - check your setup for free and explain the readiness score.
> 3. **Baseline** - install the SDK, then measure today's setup and report available calls, cost, and time.
> 4. **Optimize** - the paid baseline result comes first, your Traigent account after it, then a
>    bounded managed search.
> 5. **Results** - compare the runs, recommend one next step, and hand over the Traigent skills so
>    you can keep going alone.
>
> I will mark each stage with measured numbers when available. The readiness score describes your
> setup, not your agent's accuracy or an optimization result. I explain details only if action is needed.
> Baseline evidence decides the next step.

Here is what is lacking: dataset, agent, evaluation method. I will create each after you choose the task; synthetic results demonstrate the workflow, not production performance.

What should the walkthrough agent do?

> **A.** Turn a plain-English question about your singers database into a SQL query
> *(recommended - it is what your logs already show, and it grades deterministically)*
> **B.** Sort a support message into one of your six intents

Or reply `I have it` with a path - `agent: <path>`, `dataset: <path>`, `evaluation: <path>` - and I will use yours.
