# CLAUDE.md Analysis and Refactor Plan

**Date:** 2026-01-23

---

## Current State

- **Total:** 957 lines / 39KB
- **Global CLAUDE.md:** 155 lines / 5.9K (reasonable)
- **Project CLAUDE.md:** 957 lines (THIS IS THE PROBLEM)

---

## Section Breakdown by Size

| Section | Lines | Category |
|---------|-------|----------|
| What's Been Completed | 127 | Historical - MOVE OUT |
| Common Commands Reference | 102 | Reference - MOVE OUT |
| Directory Structure | 101 | Reference - MOVE OUT |
| Important Files to Review | 57 | Reference - MOVE OUT |
| Development Workflow | 51 | Reference - MOVE OUT |
| Testing | 47 | Reference - MOVE OUT |
| Current Challenges & Opportunities | 42 | Reference - MOVE OUT |
| Key Technical Details | 41 | Reference - MOVE OUT |
| Immediate Next Steps | 28 | Often stale - REMOVE |
| SEA Integration Test Framework | 27 | Reference - MOVE OUT |
| Data Sources | 26 | Reference - MOVE OUT |
| Project Status | 25 | Essential - KEEP |
| Code Style & Conventions | 25 | In global - REMOVE |
| Project Context | 24 | Essential - KEEP |
| Technical Stack | 22 | Reference - MOVE OUT |
| Data Architecture | 108 | Reference - MOVE OUT |
| Important: Current Date | 45 | Essential - KEEP |
| Project Mission | 17 | Essential - KEEP |

**Lines that could be moved out:** ~780 lines (82%)
**Lines to keep in core:** ~175 lines (18%)

---

## Proposed Split

### 1. CLAUDE_CORE.md (~175 lines)
Essential context for EVERY session:
- Project Mission (17 lines)
- Project Context (24 lines)
- Important: Current Date and Data Years (45 lines)
- Project Status summary (25 lines) - condensed version
- Key Files for common tasks (20 lines) - condensed version
- Database basics (10 lines)
- Core commands (10 lines)

### 2. CLAUDE_REFERENCE.md (archive, load on-demand)
Move all reference material:
- What's Been Completed
- Directory Structure
- Key Technical Details
- Technical Stack
- Code Style & Conventions (or rely on global)

### 3. CLAUDE_WORKFLOWS.md (load when coding)
- Development Workflow
- Common Commands Reference
- Testing commands
- Troubleshooting

### 4. CLAUDE_DATA.md (load when working with data)
- Data Sources
- Data Architecture
- SEA Integration details

---

## Implementation Steps

### Phase 1: Create new structure
1. Create `docs/claude-instructions/` directory
2. Write CLAUDE_CORE.md (~175 lines)
3. Write CLAUDE_REFERENCE.md
4. Write CLAUDE_WORKFLOWS.md
5. Write CLAUDE_DATA.md

### Phase 2: Update project CLAUDE.md
1. Replace current CLAUDE.md with CLAUDE_CORE.md content
2. Add links/instructions for loading appendices when needed

### Phase 3: Test and verify
1. Start fresh session
2. Verify core context is sufficient for basic tasks
3. Verify appendix loading works when needed

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| CLAUDE.md size | 957 lines / 39KB | ~175 lines / ~7KB |
| Token savings | - | ~80% per session startup |
| Clarity | Mixed essential/reference | Clear separation |

---

## Alternative: Aggressive Approach

If 175 lines is still too much, could go to ~100 lines:
- Mission: 5 lines (not 17)
- Date context: 10 lines (not 45)
- Project status: 10 lines (not 25)
- Core commands: 5 lines
- File references: 10 lines
- Database connection info: 5 lines

Everything else loads on-demand via `/docs` or Task agents.
