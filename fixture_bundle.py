"""Use the traced fixture map only when all candidate test identities are known."""
import hashlib
import json


def catalog_fingerprint(tests):
    return hashlib.sha256("\0".join(sorted(test["id"] for test in tests)).encode("utf-8")).hexdigest()


def load_fixture_index(static, tests, path):
    with path.open(encoding="utf-8") as f:
        bundle = json.load(f)
    if catalog_fingerprint(tests) != bundle["catalog_sha256"]:
        return static
    return bundle["index"]
