# Blast Radius comment-aware selector

This candidate selects known SQL fixture readers and skips Python comment additions after checking the diff against the pinned source, tokenizing the inserted lines, and verifying that the Python AST is unchanged. It runs all tests for runtime code edits, unrecognized patches, and fixture readers it cannot resolve. The scheduler balances the selected tests across the cheapest available worker count.

Three runs using the starter's Linux amd64 container limits produced identical output. The official sample scorer reported **648.179 simulated seconds and zero misses** across all 30 commits in each run. The score excludes container CPU time. Hidden commits can expose fixture reads missed by the static index, or tests that observe changed source line numbers or source text despite an unchanged AST.

## Run the public sample

From this directory, build and run with Docker using the official starter's mount and resource settings.

```sh
docker build --platform linux/amd64 -t buildathon-rwx-comment-entry:local .
sample=$(cd ../../starter/sample && pwd)
docker run --rm --platform linux/amd64 --network none --cpus 2 \
  --memory 4096m --memory-swap 4096m --pids-limit 256 --read-only \
  --tmpfs /tmp:rw,size=64m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges --user 65534:65534 --env HOME=/tmp \
  --volume "$sample/commits:/data/commits:ro" \
  --volume "$sample/tests.json:/data/tests.json:ro" \
  buildathon-rwx-comment-entry:local > output.jsonl
python ../../starter/score.py "$sample" "$sample/answers.json" output.jsonl
```

## Source and license

`sqlglot-source.zip` contains only the tracked Python source files under `sqlglot/` from [SQLGlot at commit eb11aec](https://github.com/tobymao/sqlglot/tree/eb11aec4be8cb2122afe713a4816662c3f0fb2fa). All 184 files were checked byte for byte against that commit. Its unmodified MIT notice, copyright 2026 Toby Mao, is in `LICENSE.sqlglot`. The fixture index comes from AST analysis of upstream test code at the same commit. The Docker image contains no test labels, sample patches, or repository metadata. The selector code is released under the MIT License in `LICENSE`.
