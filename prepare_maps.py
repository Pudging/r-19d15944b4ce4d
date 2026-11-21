"""Serialize the team's pinned JSON maps once during image construction."""

import gzip
import json
import marshal
from pathlib import Path


def load_maps(root):
    cache = root / "analysis.bin"
    if cache.is_file():
        return marshal.loads(cache.read_bytes())
    result = []
    for name in ("dialects", "scopes", "lines", "observed", "semantics"):
        with gzip.open(root / (name + ".json.gz"), "rt", encoding="utf-8") as stream:
            result.append(json.load(stream))
    return result


if __name__ == "__main__":
    root = Path(__file__).parent
    maps = load_maps(root)
    with (root / "analysis.bin").open("wb") as stream:
        marshal.dump(maps, stream)
