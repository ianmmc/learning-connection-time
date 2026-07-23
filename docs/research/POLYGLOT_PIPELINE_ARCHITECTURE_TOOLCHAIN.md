# Polyglot Pipeline Architecture Toolchain
## Dependency Analysis, Contract Enforcement, and Agent Integration for Mixed-Language, Multi-Process Pipelines

***

> **Note added 2026-07-23 (REQ-164 receipts):** this report's Part 3 (cross-language/cross-process
> tracking) is exactly the class of gap the pipeline's file-based receipt convention now lives in.
> `common/receipts.py::write_receipt` already reserves a `writer` tag (`py` | `node`) for this — the
> filename grammar is `<basename>.<fs_stamp>.<writer>-<h8>.json`, and cross-language hash agreement is
> deliberately NOT required (the writer tag keeps the two self-evidently distinct; see REQ-164's
> acceptance criteria in `docs/REQUIREMENTS.yaml`). The Node-side writer/resolver counterpart (for Stage
> 3's `captures.json` and Stage 2's `candidates.json`, both of which cross the Python↔Node boundary) is
> unbuilt — tracked as epic #617's sub-issue #623, which should declare the contract in
> `arch-manifest.json` per this report's Part 3/6 recommendations.

## Executive Summary

No single tool covers the full dependency surface of a polyglot pipeline with subprocess invocations, shared configuration, and file-based data contracts. The practical answer is a layered toolchain: language-specific static analyzers enforcing intra-package architecture contracts, a hand-declared interface manifest as the ground truth for cross-boundary couplings, contract tests that validate that manifest at runtime, and an MCP-backed code-intelligence server for agent-driven structural queries. The cross-language/cross-process gap is real — no mature tool closes it automatically — and the most defensible approach at the current state of tooling is a combination of architecture-as-code conventions plus executable fitness functions in CI. This report covers each layer in order: (1) Python static analysis, (2) JS/TS static analysis, (3) cross-boundary tracking, (4) dynamic-import blind spots and the packaging fix, and (5) agent-integration architecture.

***

## Part 1: Python — Intra-Package Dependency Analysis and Contract Enforcement

### grimp + import-linter: The Production Stack

The canonical Python architecture-enforcement stack is **grimp** (the graph builder) underneath **import-linter** (the contract engine). They are maintained in tandem — import-linter's `pyproject.toml` requires `grimp>=3.7`, and the latest import-linter v2.3 (released March 2025) builds on grimp 3.x. grimp constructs a queryable directed import graph of one or more installable packages, exposing it as an `ImportGraph` API with methods for path queries, descendant enumeration, and cycle detection. import-linter sits on top and lets you declare architecture contracts in `pyproject.toml` or `.importlinter` — supporting **Forbidden**, **Layers**, **Independence**, **Protected**, and **Acyclic Siblings** contract types, plus an extension point for custom contract types.[^1][^2][^3]

The CLI entry point is `lint-imports`, which exits non-zero on contract violations, making it trivially CI-integrable. Output is plain text by default, suitable for agent parsing. There is no native JSON output from `lint-imports` itself, but the underlying grimp API is fully programmable in Python — a wrapper script calling `grimp.build_graph(...)` and serializing the result to JSON gives an agent a complete, machine-readable import graph. The `grimp-tools` package (v0.4.0, April 2026) extends this with CLI commands including `grimp-tools analyze --exit-on-cycles`, `grimp-tools snapshot save/diff` (JSON diffs of the import graph across git refs), and a coupling-metrics contract type that functions as an architectural ratchet — coupling can decrease but not increase.[^4][^5]

**Practical adoption signals:** import-linter has been in continuous development since 2019 with regular releases through 2025. grimp underpins it and is also a stable, BSD-licensed library. Both are used in production Django/Python shops. They are the closest Python equivalent to ArchUnit-style contract enforcement.[^6][^5][^1]

**For a 9-stage pipeline**, the recommended contract structure is a `layers` contract asserting stage ordering (stage_1 → stage_2 → ... → stage_9), a `forbidden` contract preventing any stage from importing the LCT/database layer's internal modules directly (enforcing the boundary), and an `independence` contract among stages that should not know about each other. The SQLAlchemy/Postgres layer should be a separate root package in the import-linter config.

### pydeps: Structural Visualization with JSON-Friendly Output

**pydeps** produces module dependency graphs for an installable Python package. Its primary output is SVG/PNG visualizations, but it can emit raw dependency data via its Python API (`pydeps.depgraph`) and supports `--show-deps` to dump a JSON-serializable structure. It is better treated as a secondary verification tool (visual confirmation of what import-linter enforces) than a primary contract engine, but its graph output is useful for bootstrapping an agent's mental model of the module structure.[^7][^8]

### vulture: Dead-Code Surfacing, Not Dependency Enforcement

**vulture** is a static analyzer for finding unused Python code — classes, functions, variables. It does not do import-graph analysis or architecture contracts. Its relevance here is narrower: after restructuring the pipeline to use proper package imports (see Part 4), vulture can flag dead entry points and orphaned modules that accumulate in legacy stage-based pipelines. It supports `--min-confidence` and a whitelist mechanism to suppress expected false positives from dynamic patterns. Its output format is lint-style text (`file:line: unused function 'foo'`), parseable but not JSON. It is a useful supplementary tool but does not address the core architecture-contract requirement.[^9][^10]

### Python Static Analysis Tool Matrix

| Tool | Primary Function | Machine-Readable Output | CI-Gate | Handles Dynamic Imports | Maturity |
|---|---|---|---|---|---|
| **import-linter** | Architecture contracts | Text (exit code) / Python API → JSON | ✅ (`lint-imports`) | ❌ (static only) | High (2019–2025, active) [^6][^2] |
| **grimp** | Import graph builder / API | Python API → serializable dict | Via import-linter | ❌ | High (underpins import-linter) [^3] |
| **grimp-tools** | Snapshot diffs, coupling ratchet | JSON snapshots | ✅ (`--exit-on-cycles`) | ❌ | Emerging (2025–2026) [^4] |
| **pydeps** | Visual dependency graph | Python API / `--show-deps` | Partial | ❌ | Moderate (2013–present) [^7][^8] |
| **vulture** | Dead code detection | Lint-style text | ✅ (exit code) | ❌ (heavy false positives) | High (2017–2024, active) [^9][^10] |

***

## Part 2: JavaScript/TypeScript — dependency-cruiser vs. madge vs. skott

### dependency-cruiser: The Clear Winner for Agent-Driven Use

**dependency-cruiser** is the best-in-class choice for machine-readable, enforcement-oriented JS/TS dependency analysis. It has been actively maintained since 2016, supports ES6, CJS, AMD, TypeScript (pre- and post-compilation), LiveScript, and CoffeeScript, and produces a **formally specified, schema-validated JSON output** via `-T json`. The output schema includes a `modules` array (each source file with its direct dependencies, resolved paths, and dependency type) and a `summary` section with violation counts and the applied ruleset. This is exactly what an LLM agent needs: a stable, machine-readable structure with a documented schema.[^11][^12][^13]

The rule engine supports `forbidden`, `required`, `allowed`, and `allowed-max-depth` rule types, expressed as regular-expression-based path matchers, and violations appear directly in the JSON output. For a Playwright capture layer, the recommended configuration enforces that no module outside the designated capture package imports Playwright internals, and that test utilities do not leak into production paths. The `@toolbox-ts/depcruiser` wrapper (2025) provides a TypeScript-first API with structured output types and GitHub Actions annotations for inline PR feedback.[^14][^15][^11]

**Agent integration:** the headless invocation is `depcruise --output-type json --config .dependency-cruiser.js <path> > deps.json`. The JSON schema is published at `src/schema/cruise-result.schema.json` in the repo, so an agent can validate its own parsed output. A SARIF reporter is not natively built-in to dependency-cruiser, but the JSON output is rich enough that an agent wrapper can trivially translate violations into SARIF format for GitHub Advanced Security integration.[^13]

### madge: Established but Showing Age

**madge** (10K+ GitHub stars) is the older, more widely known tool. It generates CommonJS, AMD, or ES6 dependency graphs and outputs JSON. It is well-known and battle-tested but sees significantly less active development than dependency-cruiser — its last substantive mention in the comparison literature is from 2024–2025, and it lacks dependency-cruiser's enforcement rules (madge graphs; dependency-cruiser *enforces*). For an enforcement-oriented agent pipeline, madge is the visualization tool, not the contract engine.[^16]

### skott: Capable API, Narrower Adoption

**skott** was introduced as "the new Madge" and offers a programmatic API for graph traversal, circular dependency detection, and dead-code identification. It exposes an API (`skott()` returning `findCircularDependencies`, `findParentsOf`, `findLeaves`, etc.) rather than a config-rule system. Weekly downloads have grown but its adoption footprint is far smaller than dependency-cruiser's. For a machine-driven pipeline where an agent needs to *query* the graph programmatically rather than enforce named rules, skott's API design is attractive. For an enforcement-oriented workflow with CI gates and declared contracts, dependency-cruiser's rule engine is more appropriate. The practical recommendation is dependency-cruiser as primary, skott as a potential supplementary query API if the agent needs programmatic graph traversal that goes beyond rule checking.[^17][^18][^16]

### JS/TS Static Analysis Tool Matrix

| Tool | Enforcement Rules | JSON Output | Stable Schema | Active (2025) | Best For |
|---|---|---|---|---|---|
| **dependency-cruiser** | ✅ (rich rule engine) | ✅ (schema-validated) | ✅ | ✅ [^11][^12] | CI enforcement + agent parsing |
| **madge** | ❌ (visualization) | ✅ | Partial | Slower [^16] | Quick visualization |
| **skott** | ❌ (API queries) | ✅ (via API) | Partial | ✅ [^17] | Programmatic graph queries |

***

## Part 3: Cross-Language / Cross-Process / Cross-File Dependency Tracking

This is the hardest part, and the honest answer is: **no mature, production-ready tool automatically tracks subprocess invocations, shared config reads, and file-based handoffs as a unified dependency graph.** The tooling landscape breaks into three categories below.

### What Tools Exist (and Their Limits)

**PolyCruise** (academic, GitHub: awen-li/PolyCruise) is a research prototype for cross-language dynamic information flow analysis. It traces data flows across language boundaries at runtime using a combination of language-specific symbolic dependency analysis and language-agnostic online data flow tracking. It is not production-tooling and has no stable CLI or JSON output suitable for a CI gate. It establishes that the problem is solvable in theory but does not give you an operational tool.[^19]

**datacontract-cli** (PyPI: `datacontract-cli`) is the most relevant *semi-applicable* tool. It implements the Data Contract Specification (YAML-based), with CLI commands for `test`, `lint`, `diff`, and `breaking` (to detect breaking schema changes). Its `export --format jsonschema` emits the contract as a JSON Schema. This is directly applicable to the file-based handoff problem: declare each stage's output artifact as a `datacontract.yaml`, use `datacontract test` in CI to validate that a stage's output conforms to the contract before the next stage consumes it. It is not a dependency tracker, but it is a contract enforcer for the file-based data contracts.[^20]

**Architecture-as-code / C4 + Structurizr**: The Structurizr DSL allows declaring components, containers, and their relationships (including `subprocess`, `reads-config`, `reads-file` relationship types you define) in a structured text format that exports to JSON. This gives you a human-declared, machine-readable architecture model. Tools like the Structurizr CLI can validate that the declared model is self-consistent and generate documentation. What it cannot do is automatically verify that the code matches the declarations — it is documentation with a machine-readable format, not a live analysis.[^21]

**Fitness functions (evolutionary architecture)** are the current state of the art for enforcing cross-boundary architectural properties in CI. In the Ford/Parsons/Kua framing, a fitness function is any automated check — a pytest test, a shell script, a schema validator — that verifies an architectural property. For a subprocess invocation from Python to Node, a fitness function could be: a test that subprocess calls are only made via a wrapper module (import-linter ensures no direct `subprocess.Popen` in business logic modules), combined with a test that the invocation pattern matches the declared interface manifest. For shared config reads: a test that validates `config/*.json` conforms to a defined JSON Schema, run by both the Python and Node test suites.[^22][^21]

### The Recommended Pattern: Interface Manifest + Contract Tests

Given that no tool provides automatic cross-language dependency graph generation for subprocess/file/config couplings, the recommended approach is:

1. **Declare an `arch-manifest.json`** at the repo root enumerating all cross-boundary couplings explicitly:
   - Python→Node subprocess invocations (script path, argument schema, expected exit codes)
   - Python→CLI invocations (e.g., `claude -p`, argument schema)
   - Shared config files consumed by each language (file path, JSON Schema ref)
   - File-based stage handoffs (producer stage, consumer stage, artifact path pattern, JSON Schema ref)

2. **Write fitness-function tests** that verify the manifest against the actual code:
   - A pytest test that scans `subprocess.run/Popen/call` calls in the Python codebase (via AST or grep) and asserts each one appears in the manifest
   - A Node test that scans `child_process.spawn/exec` and `fs.readFileSync` on config paths and asserts manifest coverage
   - A JSON Schema validator run on each stage's output artifact before the next stage starts

3. **Run these in CI as a dedicated "architecture gate" step** before functional tests, blocking merge on violations.

This is not glamorous, but it is proven, maintainable, and LLM-agent-consumable (the manifest is a JSON file the agent can read and reason about directly).

### Why No Unified Cross-Language Tool Exists (Yet)

The fundamental obstacle is that subprocess invocations, config reads, and file handoffs are all *semantic* couplings, not syntactic ones that a parser can mechanically identify. A Python string like `subprocess.run(["node", script_path, ...])` requires value tracking to connect `script_path` to an actual file, which requires either dynamic analysis (expensive) or a narrow, opinionated static analysis of specific patterns. Tools like PolyCruise do this dynamically in a research setting, but no production tool has productized the full pipeline for arbitrary polyglot projects. The gap between "there is a Node subprocess call here" and "this call invokes the Playwright layer with this schema" is currently bridged only by human-declared manifests and contract tests.[^19]

***

## Part 4: Dynamic Imports and `sys.path` — How Bad Is It, and Does Packaging Fix It?

### How Much Do Dynamic Imports Defeat Static Analyzers?

The impact is significant but bounded. For tools like **import-linter** and **grimp**, the analysis is purely static — they parse `import X` and `from X import Y` statements. Any import that is constructed at runtime (e.g., `importlib.import_module(f"pipeline.stage_{n}")`, or an import inside a function body that is conditional) is invisible to these tools. `sys.path.insert(...)` is doubly problematic: it not only makes the import dynamic, but it means the module's package identity is unstable — the same file could be imported as `stage_3` or as `pipeline.stage_3` depending on runtime path state, which makes it impossible for a static tool to build a reliable graph.[^23][^3]

In a 9-stage pipeline with per-stage modules, the common pattern of `sys.path.insert(0, os.path.dirname(__file__))` plus `import stage_utils` means the import graph is undefined from a static analysis perspective. import-linter and grimp will either miss these imports entirely or report errors because the module cannot be resolved. The coverage loss depends on how pervasive the dynamic pattern is, but in a project that relies on it systematically for inter-stage imports, static analysis coverage of inter-stage dependencies could be near zero.[^3]

### Does Packaging Fix It?

**Yes, materially.** Converting the project to a proper installable package (with `pyproject.toml`, a single top-level namespace like `pipeline`, and submodules `pipeline.stages.stage_1` through `pipeline.stages.stage_9`) achieves several things:

- All imports become `from pipeline.stages.stage_3 import X`, which are fully static and resolvable by grimp[^23][^3]
- import-linter can be configured with `root_packages = ["pipeline", "lct_database"]` and will build a complete, reliable graph[^2]
- The coupling between stages becomes visible, enumerable, and enforceable via layer/independence contracts
- `sys.path.insert` can be removed entirely; the package is installed in editable mode (`pip install -e .`) in dev

The accuracy improvement for static tools is not incremental — it is categorical. The tools go from "partially blind" to "fully reliable" for intra-package imports. For in-function imports that remain (e.g., deferred loading for performance), these will still be invisible to static analyzers, but they can be flagged separately by a simple AST scan for `import` statements inside function bodies and reported in the manifest.

### Tools with Better Dynamic Import Handling

No static analyzer handles truly dynamic imports well. However, a few approaches offer partial improvement:[^9]

- **pyright** (Microsoft's type checker) performs data-flow analysis within function bodies and can sometimes resolve `importlib.import_module` calls with constant string arguments. It is not a dependency-graph tool per se, but its output (as JSON diagnostics) can supplement grimp's graph for pattern validation.
- **AST-based scanning** with Python's `ast` module: write a custom walker that extracts all `import` statements regardless of location (top-level or in-function) and all `importlib.import_module` calls, emitting them as a JSON list. This gives an agent a complete picture of what imports exist, even if some are dynamic and unresolvable. This approach is a deliberate fitness function, not a static analyzer replacement.
- **Vulture's approach** of ignoring scopes and scanning token names means it will surface dynamically-imported names that are used, but it cannot construct the import graph.[^9]

The bottom line: **packaging is the single highest-leverage action for improving static analysis coverage**, and it is recommended before adding any other tooling.

***

## Part 5: Agent Integration — JSON/SARIF, CI Gates, and MCP Servers

### Output Format Strategy

For an LLM agent that monitors and manages the repo, the recommended output hierarchy is:

1. **Structured JSON as the primary consumption format.** Both dependency-cruiser (`-T json`) and a grimp-backed Python script emit well-structured JSON. Store these as artifacts in CI runs (e.g., `deps-py.json`, `deps-ts.json`, `arch-violations.json`) and make them available to the agent via a file-read tool or MCP.

2. **SARIF as the GitHub/CI integration format.** SARIF (Static Analysis Results Interchange Format, OASIS standard) is the interchange format GitHub natively understands for code scanning results. It is richer than plain text and can be rendered as inline PR annotations. dependency-cruiser's JSON output can be translated to SARIF via a thin wrapper (the violation structure maps directly). GitHub Actions consumes SARIF via `github/codeql-action/upload-sarif@v3`. This is the bridge between local agent analysis and GitHub PR review.[^24]

3. **Pre-commit hooks as the developer-facing gate.** Both `lint-imports` and `depcruise` work as pre-commit hooks. import-linter explicitly documents pre-commit integration. This catches violations locally before CI.[^5]

4. **CI architecture gate as the enforcement layer.** A dedicated workflow job running `lint-imports`, `depcruise --output-type json`, `datacontract test`, and the fitness-function test suite, blocking merge on any failure. The JSON outputs from this job are archived and available for agent consumption.

### Code-Intelligence MCP Servers

The MCP server landscape for code intelligence has consolidated around a few viable options as of mid-2026:[^25]

**codebase-memory-mcp** (DeusData, open source, single static binary) is the highest-signal option for a polyglot repo. It indexes 158 languages via Tree-Sitter into a persistent SQLite knowledge graph, exposes 14 MCP tools including `search_graph`, `trace_call_path`, `query_graph`, and `get_architecture`, and runs with sub-millisecond query latency. A peer-reviewed evaluation across 31 languages found 0.83 quality vs. 0.92 for a file-exploration agent, with 10× fewer tokens and 2.1× fewer tool calls. It has shallow memory (git-SHA-aware diff tracking) and requires no external database. For a polyglot Python + Node pipeline, it provides the structural graph layer that the static analyzers cannot: an agent can ask "what files read config/base.json?" and get an answer grounded in the indexed graph rather than a grep scan.[^26][^27][^28][^29]

**Code Pathfinder** (Apache-2.0, Homebrew/pip install) focuses on Python with deep 5-pass AST analysis, generating bidirectional call graphs and resolving imports to actual file locations. Its 6 MCP tools (`find_symbol`, `get_callers`, `get_callees`, `resolve_import`, etc.) are precisely what an agent needs for Python-specific structural queries. It is Python-only (JS/TS support is planned), so it is a complement to codebase-memory-mcp rather than a replacement — Code Pathfinder for deep Python semantics, codebase-memory-mcp for polyglot structural queries.[^30][^31][^32]

**GitNexus** (KuzuDB-backed, 14 languages) offers Cypher-style graph queries against the codebase, which is the most expressive query surface of any server in the landscape. It carries a PolyForm Noncommercial 1.0 license, which means commercial use requires a separate license from Akon Labs — review this carefully before adoption.[^25]

**Serena** (MIT, LSP-backed, 40+ languages) wraps Language Server Protocol implementations to provide rename/references/definition signals as MCP tools. For a project with Python and TypeScript, this means configuring pylsp (or pyright) and ts-server as backends. It is configuration-heavy but offers the highest semantic precision for definition and reference lookups across both languages.[^25]

**dependency-mcp** (mkearl, MIT) is a lighter-weight MCP server that analyzes TypeScript, JavaScript, C#, Python, and more, inferring architectural layers and outputting JSON or DOT dependency graphs. It is less mature than codebase-memory-mcp but is directly architected for the architectural-layer analysis use case.[^33][^34]

### MCP Server Comparison for This Use Case

| Server | Languages | Polyglot | Structural Graph | Memory | License | Install Complexity |
|---|---|---|---|---|---|---|
| **codebase-memory-mcp** | 158 (Tree-Sitter) | ✅ | ✅ (SQLite KG) | Shallow [^27][^28] | Open source | Single binary |
| **Code Pathfinder** | Python (JS planned) | ❌ | ✅ (AST, 5-pass) | None [^32] | Apache-2.0 | Homebrew/pip |
| **GitNexus** | 14 | ✅ | ✅ (Cypher/KuzuDB) | None [^25] | PolyForm NC | Requires KuzuDB |
| **Serena** | 40+ (via LSP) | ✅ | Partial | None [^25] | MIT | Requires per-lang LSP |
| **dependency-mcp** | TS/JS/C#/Py | ✅ | ✅ (JSON/DOT) | None [^34] | MIT | npm |

***

## Part 6: Recommended Toolchain and Gap Map

### Concrete Toolchain

**Python layer:**
- `import-linter` + `grimp` for intra-package architecture contracts (layers, forbidden, independence); configure after packaging conversion
- `grimp-tools` for snapshot diffs in CI (detect new inter-module edges on each PR)
- A custom `ast`-based fitness function (< 50 lines of Python) that enumerates all in-function imports and `subprocess` call sites and asserts manifest coverage

**JS/TS layer:**
- `dependency-cruiser` with a `.dependency-cruiser.js` config and `-T json` output for machine-readable enforcement; rules configured to enforce that the Playwright capture layer does not import from pipeline-side paths

**Cross-boundary layer:**
- `arch-manifest.json` hand-declared at repo root, covering all subprocess invocations, config reads, and file handoffs with JSON Schema refs
- `datacontract-cli` validating each stage's output artifact schema before handoff to the next stage
- Fitness-function test suite (pytest + jest) asserting manifest completeness and schema conformance

**Agent layer:**
- `codebase-memory-mcp` as the primary structural query server (polyglot, single binary, low overhead)
- `Code Pathfinder` for deep Python call-graph and import-resolution queries
- CI artifacts (`deps-py.json`, `deps-ts.json`, `arch-violations.json`, `arch-manifest.json`) published as downloadable artifacts per run for agent consumption
- SARIF output from the architecture gate job uploaded to GitHub code scanning for PR-level visibility

### Where No Good Tooling Exists (Cover with Conventions)

The following gaps are real and are not covered by any production-ready tool as of mid-2026. Cover each with the convention described:

| Gap | Best Current Approach |
|---|---|
| Automatic detection of Python→Node subprocess couplings | AST scan for `subprocess.*` + manifest assertion fitness function |
| Automatic detection of shared-config reads across languages | Grep/AST scan both Python and JS for config path strings + manifest assertion |
| Unified cross-language dependency graph (single JSON) | Not available. `arch-manifest.json` + codebase-memory-mcp as approximate substitute |
| Dynamic import resolution in import-linter/grimp | Not available. Convert to installable package to eliminate the pattern |
| File-handoff schema drift detection across pipeline stages | `datacontract-cli` with per-stage YAML contracts in CI |
| Automatic subprocess argument schema extraction | Not available. Declare argument schemas in manifest by hand; validate in contract tests |

The absence of a unified cross-language dependency graph tool is the largest gap. It is not a tooling failure that can be worked around with more tooling — it is a fundamental limitation of static analysis for semantic couplings that cross runtime boundaries. The manifest-plus-contract-tests approach described above is not a compromise; it is the current state of the art for this shape of problem, used by teams maintaining polyglot pipelines at scale.

---

## References

1. [import-linter/pyproject.toml at master · seddonym/import-linter](https://github.com/seddonym/import-linter/blob/master/pyproject.toml) - Import Linter allows you to define and enforce rules for the internal and external imports within yo...

2. [Home](https://import-linter.readthedocs.io/en/v2.10/) - Lint your Python architecture.

3. [Usage - Grimp 3.14 documentation](https://grimp.readthedocs.io/en/stable/usage.html) - Grimp provides an API in the form of an ImportGraph that represents all the imports within one or mo...

4. [grimp-tools 0.4.0 on PyPI - Libraries.io - security & maintenance data ...](https://libraries.io/pypi/grimp-tools) - Dependency analysis, coupling enforcement, and architectural contract visualization for Django/Pytho...

5. [Linter for Python Architecture - Roman Imankulov](https://roman.pt/posts/python-architecture-linter/) - How do you enforce architecture for your Python and Django projects other than in code reviews or gu...

6. [Changelog](https://import-linter.readthedocs.io/en/v2.2/changelog.html)

7. [pydeps](https://pypi.org/project/pydeps/1.4.0/) - Display module dependencies

8. [thebjorn/pydeps: Python Module Dependency graphs](https://github.com/thebjorn/pydeps) - Python Module Dependency graphs. Contribute to thebjorn/pydeps development by creating an account on...

9. [searches for unused ("dead") code in a Python program](https://manpages.ubuntu.com/manpages/resolute/man1/vulture.1.html)

10. [vulture](https://pypi.org/project/vulture/) - Find dead code

11. [GitHub - sverweij/dependency-cruiser: Validate and visualize dependencies. Your rules. JavaScript, TypeScript, CoffeeScript. ES6, CommonJS, AMD.](https://github.com/sverweij/dependency-cruiser) - Validate and visualize dependencies. Your rules. JavaScript, TypeScript, CoffeeScript. ES6, CommonJS...

12. [dependency-cruiser/doc/output-format.md at main · sverweij/dependency-cruiser](https://github.com/sverweij/dependency-cruiser/blob/main/doc/output-format.md) - Validate and visualize dependencies. Your rules. JavaScript, TypeScript, CoffeeScript. ES6, CommonJS...

13. [dependency-cruiser/src/schema/cruise-result.schema.json at main · sverweij/dependency-cruiser](https://github.com/sverweij/dependency-cruiser/blob/main/src/schema/cruise-result.schema.json) - Validate and visualize dependencies. Your rules. JavaScript, TypeScript, CoffeeScript. ES6, CommonJS...

14. [@toolbox-ts/depcruiser - npm](https://www.npmjs.com/package/@toolbox-ts/depcruiser) - Dependency cruiser utilities.. Latest version: 0.1.1, last published: 4 days ago. Start using @toolb...

15. [dependency-cruiser/doc/faq.md at main · sverweij/dependency-cruiser](https://github.com/sverweij/dependency-cruiser/blob/main/doc/faq.md) - Validate and visualize dependencies. Your rules. JavaScript, TypeScript, CoffeeScript. ES6, CommonJS...

16. [skott vs madge - compare differences and reviews? - LibHunt](https://www.libhunt.com/compare-skott-vs-madge)

17. [Introducing Skott, the new Madge! - DEV Community](https://dev.to/antoinecoulon/introducing-skott-the-new-madge-1bfl) - Skott is a tool that generates a graph of dependencies from your JavaScript/TypeScript/Node.js proje...

18. [Thanks @frolovdev :) dependency-cruiser is a great tool ...](https://dev.to/antoinecoulon/comment/22bd0) - Little announcement: thanks for anyone showing interest in skott! Just for your own information,...

19. [GitHub - awen-li/PolyCruise: A Cross-Language Dynamic Information Flow Analysis.](https://github.com/awen-li/PolyCruise) - A Cross-Language Dynamic Information Flow Analysis. - awen-li/PolyCruise

20. [datacontract-cli](https://pypi.org/project/datacontract-cli/0.9.0/) - Validate data contracts

21. [Building Evolutionary Architectures (short summary) — System Design Space](https://system-design.space/en/chapter/evolutionary-arch-book/) - Fitness Functions for Architectural Verification, Connascence, Architectural Quantum and Database Ev...

22. [Implementing a Staged Approach to Evolutionary ...](https://www.infoq.com/articles/implementing-evolutionary-architecture/) - The evolution of software architecture needs new approaches for continuous planning, facilitating co...

23. [Usage](https://import-linter.readthedocs.io/en/stable/usage.html)

24. [[PDF] Static Analysis Results Interchange Format (SARIF) Version 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/csprd01/sarif-v2.1.0-csprd01.pdf)

25. [Best MCP Servers for Code Intelligence: Honest Comparison of 12 ...](https://sverklo.com/blog/practical-guide-mcp-code-intelligence/) - 12 MCP code-intelligence servers compared on license, hosting, language coverage, tool count, and re...

26. [DeusData/codebase-memory-mcp ...](https://github.com/DeusData/codebase-memory-mcp) - High-performance code intelligence MCP server. Indexes codebases into a persistent knowledge graph —...

27. [Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via ...](https://memorypapers.org/papers/codebase-memory-tree-sitter-based-knowledge-graphs-for-llm-code-exploration-via-mcp) - Codebase-Memory uses a Tree-Sitter-based knowledge graph in SQLite exposed via MCP tools to answer c...

28. [codebase-memory-mcp: The C-Built Knowledge Graph That Makes ...](https://repodaily.xyz/projects/2026-06-19/codebase-memory-mcp/) - A pure-C MCP server that indexes 158 languages into a persistent graph in milliseconds, slashes toke...

29. [This MCP Server Cuts AI Agent Tokens By 99%](https://www.youtube.com/watch?v=eo6fSQBMo4Q) - Your AI coding agent wastes most of its tokens reading files one by one. codebase-memory-mcp indexes...

30. [MCP Tools API Reference - 6 Powerful Code ... - Code Pathfinder](https://codepathfinder.dev/docs/mcp/tools-reference) - Complete reference for 6 code intelligence tools - call graphs, symbol search, import resolution

31. [MCP Server Configuration Guide - Advanced ... - Code Pathfinder](https://codepathfinder.dev/docs/mcp/configuration) - Advanced MCP server setup - HTTP transport, Docker, multi-project configuration

32. [Stop Grepping, Start Querying: MCP Server for Code- ...](https://codepathfinder.dev/blog/mcp-server-code-pathfinder) - Connect Code-Pathfinder's indexed code analysis directly to Claude Code, Codex, and MCP-enabled AI a...

33. [Dependency Analysis - MCP Server - MagicSlides](https://www.magicslides.app/mcps/mkearl-dependency-tracker) - Manage and analyze project dependencies, offering caching and flexible configuration for efficient t...

34. [dependency-mcp](https://www.mcpserverfinder.com/servers/mkearl/dependency-mcp) - A Model Context Protocol (MCP) server for analyzing code dependencies

