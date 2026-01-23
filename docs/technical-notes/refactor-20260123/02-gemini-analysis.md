# Gemini Architecture Analysis

**Date:** 2026-01-23
**Source:** Gemini consultation via MCP

---

## Key Problem Identified

**Overloading Claude with Redundant Information:**
- Loading `CLAUDE.md` (39KB) and `REQUIREMENTS.yaml` (~25KB) into *every* conversation is highly inefficient
- Much of this information is static and doesn't need to be repeated for every task
- Methodology and bell schedule docs are large and probably don't need to be loaded every time

---

## Gemini's Recommendations

### 1. "Need-to-Know" Context Loading

- **Stop loading full CLAUDE.md into every session**
- Create smaller, core instruction file (`CLAUDE_CORE.md`) with essentials
- Load REQUIREMENTS.yaml only when working on features directly related to specific requirements

### 2. Modularize and Chunk Tasks

- Break down large tasks into smaller, well-defined sub-tasks
- Provide only *relevant* code snippets for each sub-task

### 3. Prompt Engineering

- Use clear, concise prompts
- State the goal explicitly
- Provide examples of expected input/output
- Ask specific questions rather than open-ended ones

### 4. Database Interaction Optimization

- Never send entire database extracts
- Use targeted SQL queries
- Summarize or sample data before providing to Claude

### 5. External Tool Usage

- Use standard Python libraries for data transformations
- Use Claude to *generate* the code, then run it locally

### 6. Selective Documentation

- Avoid loading entire documentation files
- Extract specific sections relevant to the task
- Consider creating a lookup function for on-demand doc loading

---

## Suggested File Splitting Strategy

### CLAUDE.md Should Be Split By:

1. **By Topic:**
   - `CLAUDE_CORE.md` - Essential project context only
   - `CLAUDE_DATA_SOURCES.md` - Data source details
   - `CLAUDE_PIPELINE_STEPS.md` - Pipeline documentation
   - `CLAUDE_SEA_INTEGRATION.md` - State-specific details

2. **By Responsibility:**
   - `CLAUDE_TESTING.md` - Test-related instructions
   - `CLAUDE_CODE_GENERATION.md` - Coding patterns

3. **Dynamic Loading:**
   - Load only relevant instruction files based on task

---

## Recommended Best Practices

1. **Version Control:** Use Git (already done)
2. **Iterative Development:** Don't solve everything at once
3. **Testing:** Write comprehensive tests
4. **Monitoring:** Track token usage (npx ccusage)
5. **Regular Sessions:** Start fresh sessions regularly
6. **Model Selection:** Consider if different Claude model offers better tradeoff

---

## Action Items for This Project

1. [ ] Analyze current CLAUDE.md content - what's essential vs reference?
2. [ ] Split CLAUDE.md into core + appendices
3. [ ] Create dynamic loading mechanism for docs
4. [ ] Review session startup to reduce automatic context loading
5. [ ] Check if subagents are loading full context unnecessarily
6. [ ] Implement selective REQUIREMENTS.yaml loading
