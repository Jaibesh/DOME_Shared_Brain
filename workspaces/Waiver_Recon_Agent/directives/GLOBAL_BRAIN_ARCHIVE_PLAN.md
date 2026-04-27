# Token Optimization & Subscription Consolidation Plan (v2)

## Goal
Reduce recurring AI costs and eliminate model usage limits by consolidating subscriptions and optimizing the DOME framework's token consumption across all work/personal environments.

## User Review Required

> [!IMPORTANT]
> **Subscription Consolidation Recommendation**: 
> 1. **Cancel ChatGPT Plus**: Highly redundant with Gemini Pro and Claude 3.5.
> 2. **Keep Claude Pro ($20)**: Essential for coding quality.
> 3. **Use Gemini API (Pay-as-you-go)**: Instead of a flat $125/mo plan, the API (via Vertex or AI Studio) allows for granular cost control. With the caching optimizations below, your monthly API bill will likely be <$20.

## Proposed Changes

### [DOME Framework - Global Core]
*Changes will be made to the base classes in the development hub (`Personal_Agent`) and propagated to `D:\DOME_CORE`.*

#### [MODIFY] [enhanced_supervisor.py](file:///C:/Users/robis/OneDrive/Documents/Agentic_Workflows/Personal_Agent/execution/enhanced_supervisor.py)
- **Native Context Caching (Gemini)**: 
    - Implement the `CacheManager` to store the 18+ knowledge files (MLM) as a cached prefix. This reduces cost by **~90%** for repeated turns.
- **Prompt Caching (Claude)**: 
    - Add `cache_control` blocks to system prompts and historical context.
- **RAG Refactoring**: 
    - Change "static file loading" to "dynamic retrieval." Only 2-3 relevant chunks will be injected per turn instead of all 18+ files.

#### [MODIFY] [observability.py](file:///C:/Users/robis/OneDrive/Documents/Agentic_Workflows/Personal_Agent/execution/observability.py)
- **Token Impact Dashboard**: 
    - Track "Cached Tokens" vs "Processed Tokens" to show real-time savings in logs.

---

## Verification Plan

### Automated Tests
- **Context Size Validation**: Run `tests/test_memory_efficiency.py` to ensure context remains below 5,000 tokens for long conversations.
- **Cache Hit Verification**: Verify `X-Gemini-Cache-Status: HIT` in API responses.

### Manual Verification
1. Run `MLM_solutions` demo and monitor the Gemini API dashboard. 
2. Expected Result: Token count drops from ~100k/message to ~5k/message.
