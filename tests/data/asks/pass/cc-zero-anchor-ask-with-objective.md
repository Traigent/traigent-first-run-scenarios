<!-- ask-corpus
expect: pass
material: true
source: component-creation.md, When nothing anchors task intent, step 2 carries the five things of The gap-question contract on the same question; item 5, "What they want optimized", in one line, with the default said "in those words"
-->
Here is what is lacking: dataset, agent, evaluation method. I will create each after you choose the task; synthetic results demonstrate the workflow, not production performance.

What do you want optimized - correct answers, or cost too? If you name nothing, I will optimize accuracy, with cost when measurable.

What should the walkthrough agent do?

> **A.** Turn a plain-English question about your singers database into a SQL query
> *(recommended - it is what your logs already show, and it grades deterministically)*
> **B.** Sort a support message into one of your six intents

Or reply `I have it` with a path - `agent: <path>`, `dataset: <path>`, `evaluation: <path>` - and I will use yours.
