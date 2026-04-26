# Pattern: LangGraph Supervisor

## Definition
A design pattern implemented in the LangGraph library that allows for the creation of multi-agent systems by routing requests between different agents based on a supervisor's decision-making process.

## Details
The supervisor receives a request, determines which agent should handle it, and hands off the information. Agents perform tool calling and feedback loops until completion, then hand back the result.  The supervisor uses an 'output mode' to configure what information is passed back (final agent message or entire agent message history). Supervisors can also be hierarchical, managing other supervisors.

## Related Tags
`multi-agent systems`, `tool calling`, `LangGraph`, `agent routing`

*Synthesized via AI*
