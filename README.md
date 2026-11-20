# Team potato · Blast Radius

Build this Docker image and run it with the official scorer. The selector uses the Python standard library. It reads the supplied test catalog and patches and writes one JSON line per patch. The implementation was developed with Codex.

The dependency maps and source snapshot derive from the organizer's pinned SQLGlot commit `eb11aec4be8cb2122afe713a4816662c3f0fb2fa`. The selector normalizes line endings when it reads the bundled pinned source for diff matching. Toby Mao's original MIT license is included as `LICENSE.sqlglot`.

The selector combines fixture references, ordinary-comment equivalence, explicit and observed dialect dependencies, and per-test coverage of localized function edits. The coverage collector carries pytest node IDs into spawned process-pool work. Tests without reliable coverage and tests that use untracked external subprocesses remain selected for scoped changes. Changes that cannot be validated or classified run the full test suite. Worker scheduling uses the scorer's integer millisecond costs.

The official public scorer reported **321.592 simulated seconds and zero misses on all 30 sample patches**, compared with 1,210.470 seconds for the untouched starter. This sample total excludes container CPU. Hidden cases may expose unobserved dependencies, source introspection, or import-time behavior. The scorer image contains source-derived maps and the pinned source snapshot. Sample patches, expected answers, and run outputs are excluded.
