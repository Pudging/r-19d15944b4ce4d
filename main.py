"""Select proven fixture, comment, and dialect-local changes."""

import json
from pathlib import Path
from zipfile import Path as ZipPath, ZipFile

from fixture_bundle import load_fixture_index
from select_declarations import load_declarations, projected
from prepare_maps import load_maps
from scheduler import schedule
from select_observed import affected_observations
from select_lines import affected_lines
from select_dialects import localized_class_values, localized_function_values
from select_paths import comment_only, file_edits, fixture_tests
from select_resources import resource_patch, resource_readers
from select_scopes import affected_ids
from select_semantics import child_guards, refine


DATA = Path("/data")
ASSETS = Path(__file__).parent


def select_previous(patch, tests, fixture_index, source, dialects, coverage, lines, observations=None,
           resources=None, blobs=None, known_catalog=True, semantics=None):
    edits = resource_patch(patch, blobs) if resources is not None else file_edits(patch)
    if not edits:
        return tests
    if not known_catalog and any(path.startswith("tests/fixtures/") for path in edits):
        return tests
    readers = set()
    dependencies = set()
    source_importers = set()
    used_observations = False
    used_lines = False
    used_dialect = False
    used_coverage = False
    resource_only = resources is not None and all(path in fixture_index for path in edits)
    for path, diff in edits.items():
        if path in fixture_index:
            affected = fixture_index[path]
            if resource_only:
                affected = resource_readers(path, diff, affected, resources)
            readers.update(affected)
        elif (path.startswith("sqlglot/") and not any(
              line.startswith("-") and not line.startswith("--- ") for line in diff
        ) and comment_only(source / path, diff)):
            continue
        elif observations is not None and (
            result := affected_observations(path, diff, source, observations)
        ) is not None:
            dependencies.update(result)
            used_observations = True
        elif (ids := affected_lines(path, diff, source, lines)) is not None:
            dependencies.update(ids)
            used_lines = True
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
    if not (used_lines or used_dialect or used_coverage or used_observations):
        return fixtures
    numbers = {test["number"] for test in fixtures}
    seen = {test["id"] for test in tests}
    guards = coverage.get("unverified", ())
    single_source = semantics is not None and known_catalog and len(edits) == 1 and path.startswith("sqlglot/") and path.endswith(".py")
    if single_source and (used_observations or used_lines or used_coverage):
        guards = child_guards(path, diff, source, guards, semantics)
    if used_observations:
        seen.intersection_update(observations['tests'])
        dependencies.update(observations['unverified'])
        dependencies.update(guards)
    if used_lines:
        seen.intersection_update(lines["tests"])
        dependencies.update(guards)
    if used_dialect:
        seen.intersection_update(dialects["seen"])
    if used_coverage:
        seen.intersection_update(coverage["test_ids"])
        dependencies.update(guards)
    selected = [
        test for test in tests
        if test["number"] in numbers or test["id"] in dependencies
        or test["file"] in source_importers or test["id"] not in seen
    ]
    return refine(path, diff, source, selected, lines, semantics) if single_source else selected


def select(patch, tests, fixture_index, source, dialects, coverage, lines, observations=None,
           resources=None, blobs=None, known_catalog=True, semantics=None):
    def previous(text, fixture_archive=resources):
        return select_previous(text, tests, fixture_index, source, dialects, coverage, lines,
                               observations, fixture_archive, blobs, known_catalog, semantics)

    if not known_catalog or semantics is None:
        return previous(patch)
    edits = resource_patch(patch, blobs) if resources is not None else file_edits(patch)
    if not edits or not any(p.startswith("sqlglot/") and p.endswith(".py") for p in edits):
        return previous(patch)
    data = load_declarations()
    # A test must reach at least one changed site for execution to diverge.
    # For mixed patches retain full fixture readers, including format-only edits.
    selected = set()
    for path, diff in edits.items():
        if len(edits) == 1:
            prior = previous(patch)
        elif path in fixture_index:
            prior = fixture_tests(set(fixture_index[path]), tests)
            if prior is None:
                return tests
        else:
            text = f"diff --git a/{path} b/{path}\n" + "\n".join(diff) + "\n"
            prior = previous(text, None)
        if prior:
            narrowed = projected(path, diff, source, data)
            selected.update(t["id"] for t in prior if narrowed is None or t["id"] in narrowed)
    if len(selected) == len(tests):
        return tests
    return [t for t in tests if t["id"] in selected]


def main():
    tests = json.loads((DATA / "tests.json").read_text(encoding="utf-8"))["tests"]
    static_index = json.loads((ASSETS / "fixture_index.json").read_text(encoding="utf-8"))
    fixture_index = load_fixture_index(static_index, tests, ASSETS / "fixture_bundle.json")
    resource_catalog = fixture_index is not static_index
    dialects, coverage, lines, observations, semantics = load_maps(ASSETS)
    full_schedule = schedule(tests)
    with ZipFile(ASSETS / "sqlglot-source.zip") as archive, ZipFile(ASSETS / "resources.zip") as resources:
        source = ZipPath(archive)
        blobs = json.loads(resources.read("blobs.json"))
        # The full trace and pinned static reader model apply to this catalog.
        # New test identities can introduce additional readers.
        for patch in sorted((DATA / "commits").glob("*.patch")):
            try:
                selection = select(
                    patch.read_text(encoding="utf-8"), tests, fixture_index, source, dialects,
                    coverage, lines, observations, resources if resource_catalog else None,
                    blobs, resource_catalog, semantics,
                )
            except (UnicodeError, ValueError, OSError, RecursionError):
                selection = tests
            workers = full_schedule if selection is tests else schedule(selection)
            print(json.dumps({"commit": patch.stem, "workers": workers}, separators=(",", ":")))


if __name__ == "__main__":
    main()
