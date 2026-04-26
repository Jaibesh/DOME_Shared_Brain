# Pattern: Time Travel Debugging

## Definition
A debugging and operational pattern where the state of an agentic workflow is rewound to a previous checkpoint to inspect, correct, or branch execution.

## Details
Enabled by **Checkpointers** in frameworks like LangGraph.
1.  **Rewind**: Go back to step `N-1` before an error occurred.
2.  **Inspect**: Check exactly what the `State` was (variables, context).
3.  **Modify**: Manually patch the state (e.g., correct a hallucinated API argument).
4.  **Fork**: Resume execution from that point, creating a new successful history.

## Related Tags
`debugging`, `LangGraph`, `persistence`, `resiliency`

*Synthesized via AI form LangGraph Deep Dive*
