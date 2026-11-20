"""Select proven fixture, comment, and dialect-local changes."""

import gzip
import json
from pathlib import Path
from zipfile import Path as ZipPath, ZipFile

from scheduler import schedule
from select_dialects import localized_class_values, localized_function_values
from select_paths import comment_only, file_edits, fixture_tests
from select_scopes import affected_ids


DATA = Path("/data")
ASSETS = Path(__file__).parent


def select(patch, tests, fixture_index, source, dialects, coverage):
    edits = file_edits(patch)
    if not edits:
        return tests
    readers = set()
    dependencies = set()
    source_importers = set()
    used_dialect = False
    used_coverage = False
    for path, diff in edits.items():
        if path in fixture_index:
            readers.update(fixture_index[path])
        elif path.startswith("sqlglot/") and comment_only(source / path, diff):
            continue
        elif path in dialects["cases"] and (
            localized_class_values(path, diff, source)
            or localized_function_values(path, diff, source)
        ):
            dependencies.update(dialects["cases"][path])
            source_importers.update(dialects["files"].get(path, ()))
            used_dialect = True
        elif (ids := affected_ids(path, diff, source, coverage["scopes"])) is not None:
            dependencies.update(coverage["test_ids"][index] for index in ids)
            used_coverage = True
        else:
            return tests
    fixtures = fixture_tests(readers, tests)
    if fixtures is None:
        return tests
    if not used_dialect and not used_coverage:
        return fixtures
    numbers = {test["number"] for test in fixtures}
    seen = {test["id"] for test in tests}
    if used_dialect:
        seen.intersection_update(dialects["seen"])
    if used_coverage:
        seen.intersection_update(coverage["test_ids"])
        dependencies.update(coverage.get("unverified", ()))
    return [
        test for test in tests
        if test["number"] in numbers or test["id"] in dependencies
        or test["file"] in source_importers or test["id"] not in seen
    ]


def main():
    tests = json.loads((DATA / "tests.json").read_text(encoding="utf-8"))["tests"]
    fixture_index = json.loads((ASSETS / "fixture_index.json").read_text(encoding="utf-8"))
    with gzip.open(ASSETS / "dialects.json.gz", "rt", encoding="utf-8") as stream:
        dialects = json.load(stream)
    with gzip.open(ASSETS / "scopes.json.gz", "rt", encoding="utf-8") as stream:
        coverage = json.load(stream)
    full_schedule = schedule(tests)
    with ZipFile(ASSETS / "sqlglot-source.zip") as archive:
        source = ZipPath(archive)
        for patch in sorted((DATA / "commits").glob("*.patch")):
            try:
                selection = select(
                    patch.read_text(encoding="utf-8"), tests, fixture_index, source, dialects, coverage,
                )
            except (UnicodeError, ValueError, OSError, RecursionError):
                selection = tests
            workers = full_schedule if selection is tests else schedule(selection)
            print(json.dumps({"commit": patch.stem, "workers": workers}, separators=(",", ":")))


if __name__ == "__main__":
    main()
