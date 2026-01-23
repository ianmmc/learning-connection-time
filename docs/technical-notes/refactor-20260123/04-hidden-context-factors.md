# Hidden Context Consumption Factors

**Date:** 2026-01-23
**Source:** Gemini analysis (second consultation)

---

## Beyond CLAUDE.md: Other Token Consumers

### 1. System Prompts (ALWAYS PRESENT)
- System prompts are always in context
- Need to optimize aggressively
- Often hidden from user view

### 2. Tool Definitions (Function Calling)
- **Very token-heavy**
- Every available tool's description consumes tokens
- MCP servers add tool definitions
- Minimize descriptions and examples
- Consider dynamic generation based on task

**Tools available in this project:**
- Bash, Read, Write, Edit, Glob, Grep
- Task (subagents), TodoWrite
- WebFetch, WebSearch
- Gemini MCP tools (8 tools)
- Hostinger MCP tools (many)
- claude-mem MCP tools (3-4)
- Plus skill definitions

### 3. Conversation History
- **MAJOR CULPRIT**
- Entire conversation is in context until /compact
- Even after /compact, summary still takes space
- /clear helps but loses context

**Recommendation:** Implement selective retention or vector database for history

### 4. Output Formatting
- Structured output (JSON, XML) is verbose
- Markdown with tables consumes tokens
- Consider simpler formats

### 5. Agentic Reasoning
- Complex reasoning chains consume tokens rapidly
- Design for efficiency

---

## Subagent Context Loading Issue

**Current behavior:** Subagents may be loading full project context

**Recommended:** Subagents should be **stateless** unless needed
- Pass task-specific instructions only
- Don't load CLAUDE.md into subagents
- Project context passed only when subagent needs it

---

## Multi-Tier Pipeline Optimization

Current pipeline: Playwright → PDF/OCR → Claude → Gemini (separate tiers)

**More efficient alternatives:**

1. **Chain LLMs:** Single Claude call with OCR instructions, then Gemini for analysis
2. **Specialized Models:** Investigate if one model can handle entire process
3. **Function Calling:** Claude identifies data needed, function calls process via Gemini

---

## Action Items

1. [ ] Profile token usage at each stage (use ccusage)
2. [ ] Implement dynamic context loading
3. [ ] Audit MCP tool definitions for verbosity
4. [ ] Check if subagents are loading project context
5. [ ] Consider vector database for history retrieval
6. [ ] Reduce tool count when not needed
7. [ ] Optimize output format instructions

---

## Profiling Plan

```bash
# Monitor token usage live
npx ccusage blocks --live

# Check per-model costs
npx ccusage@latest --breakdown

# Count tokens in a file
count-tokens CLAUDE.md --format json
```

---

## Quick Wins (Immediate)

1. Reduce CLAUDE.md to core only (done in plan)
2. Check MCP server tool counts
3. Use haiku for simple tasks (already in global CLAUDE.md)
4. Run /clear between distinct tasks
5. Batch related questions into single messages
