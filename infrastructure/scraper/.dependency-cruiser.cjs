/**
 * dependency-cruiser rules for the Node capture layer (REQ-098 step 5).
 * The JS analog of import-linter for the Python side. Run: `npm run lint:deps`.
 * See docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md §10.
 */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "Circular dependencies make the capture layer hard to reason about and test.",
      from: {},
      to: { circular: true },
    },
    {
      name: "no-orphans",
      severity: "warn",
      comment: "A module nothing imports (and which isn't an entry point or test) is likely dead.",
      from: { orphan: true, pathNot: ["\\.test\\.mjs$", "\\.dependency-cruiser\\.cjs$"] },
      to: {},
    },
    {
      name: "prod-not-to-test",
      severity: "error",
      comment: "Production capture code must never import a *.test.mjs file.",
      from: { pathNot: "\\.test\\.mjs$" },
      to: { path: "\\.test\\.mjs$" },
    },
    {
      name: "no-unresolvable",
      severity: "error",
      comment: "An import that can't be resolved on disk is a real bug.",
      from: {},
      to: { couldNotResolve: true },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsPreCompilationDeps: true,
  },
};
