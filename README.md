# Team potato · Blast Radius

Build this directory as a Linux AMD64 Docker image. Its default command reads the test catalog and patch files from `/data` and prints one worker schedule per patch.

The selector uses test observations and source locations from SQLGlot commit `eb11aec4be8cb2122afe713a4816662c3f0fb2fa`. Each new patch is checked against the bundled source. For localized function edits, the selector combines per-test line and function coverage, including work dispatched to spawned processes. For identity and equality operator edits, it checks whether the observed operand types can distinguish the two operations. A reached line without a corresponding operand observation retains the test. For simple dialect attribute values, the selector uses source-derived reader locations and their baseline coverage. For required expression arguments, it uses constructor observations and direct test source readers.

The fixture map covers 62 pinned fixture paths, including readers invoked by the process pool and class setup. Missing catalog identities, unverified tests and unsupported edits trigger conservative fallbacks. The bundled interpreter uses only the Python standard library at decision time.

On the organizer's 30 public sample patches, the local scorer measured 141.038 simulated seconds and zero missed commits. Three fresh Linux processes produced identical output and used 0.729, 0.752 and 0.741 CPU seconds. The preceding line-coverage selector measured 277.594 simulated seconds with zero misses. Held-out commits can exercise different paths, import-time state, source introspection and runtime types.

The SQLGlot source and derived maps retain the project's MIT license in `LICENSE.sqlglot`. The team implementation is licensed in `LICENSE` and was developed with Codex.
