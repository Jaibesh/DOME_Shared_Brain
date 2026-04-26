# Pattern: Observability via Tracing

## Definition
The practice of instrumenting AI agents to log every input, output, and intermediate thought process to a centralized dashboard (e.g., LangSmith) for debugging and datasets.

## Details
In stochastic systems (LLMs), "Unit Tests" are often insufficient. "Tracing" allows developers to look at a failed run, see exactly what the LLM generated, and add that example to a "Regression Dataset" to prevent it from happening again.

## Related Tags
`debugging`, `LangSmith`, `evals`, `ops`

*Synthesized via Antigravity form LangSmith Research*
