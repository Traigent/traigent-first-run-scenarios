<!-- ask-corpus
expect: pass
material: true
source: component-creation.md, When nothing anchors task intent, steps 2-3: what is lacking in their three words, then exactly one question, "What should the walkthrough agent do?", at most three choices with one recommended, and `I have it` carried on that same question
-->
Here is what is lacking: dataset, agent, evaluation method. I will create each after you choose the task; synthetic results demonstrate the workflow, not production performance.

What should the walkthrough agent do?

> **A.** Turn a plain-English question about your singers database into a SQL query
> *(recommended - it is what your logs already show, and it grades deterministically)*
> **B.** Sort a support message into one of your six intents

Or reply `I have it` with a path - `agent: <path>`, `dataset: <path>`, `evaluation: <path>` - and I will use yours.
