"""Apply pinned resource-reader dependencies to valid same-path Git edits."""

import json
import re

from select_paths import DIFF_HEADER, valid_text_edit
from select_scopes import apply_edit


JSON_CASES = "tests/fixtures/jsonpath/cts.json"
JSON_READER = "tests/test_jsonpath.py::test_cts_file"
INDEX = re.compile(r"index ([0-9a-f]{7,40})\.\.([0-9a-f]{7,40}) 100644")
BINARY_BLOCK = re.compile(r"(?:literal|delta) [0-9]{1,9}")
BASE85 = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~")


def valid_binary_edit(path, lines, blobs):
    """Both Git diff encodings are sufficient to establish the resource path."""
    if path not in blobs or not path.endswith(".csv.gz") or len(lines) < 2:
        return False
    header = INDEX.fullmatch(lines[0])
    if not header or not blobs[path].startswith(header[1]) or header[1] == header[2]:
        return False
    if lines[1:] == [f"Binary files a/{path} and b/{path} differ"]:
        return True
    if lines[1] != "GIT binary patch" or len(header[1]) != 40 or len(header[2]) != 40:
        return False
    # Git emits a forward and reverse block. The selection depends only on the
    # changed path, so a compressed payload never needs to be inflated or run.
    blocks = "\n".join(lines[2:]).rstrip("\n").split("\n\n")
    if len(blocks) != 2:
        return False
    for block in blocks:
        title, *payload = block.splitlines()
        if not BINARY_BLOCK.fullmatch(title) or not payload:
            return False
        for line in payload:
            if not line:
                return False
            index = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz".find(line[0])
            if index < 0 or len(line) != 1 + 5 * ((index + 4) // 4) or not set(line[1:]) <= BASE85:
                return False
    return True


def resource_patch(patch, blobs):
    """Handle mixed text/binary patches without accepting unknown binary formats."""
    edits = {}
    current = None
    for line in patch.removesuffix("\n").split("\n"):
        if line.startswith("diff --git "):
            header = DIFF_HEADER.fullmatch(line)
            if not header or header[1] != header[2] or header[1] in edits:
                return None
            current = []
            edits[header[1]] = current
        elif current is None:
            return None
        else:
            current.append(line)
    for path, lines in edits.items():
        if not (valid_text_edit(path, lines) or valid_binary_edit(path, lines, blobs)):
            return None
    return edits


def json_inputs(text):
    """Values read by the pinned JSONPath conformance test, in iteration order."""
    cases = json.loads(text)["tests"]
    if not isinstance(cases, list):
        raise ValueError("Unexpected conformance data")
    inputs = []
    for case in cases:
        name, selector, invalid = case["name"], case["selector"], case.get("invalid_selector", False)
        if not (isinstance(name, str) and isinstance(selector, str) and isinstance(invalid, bool)):
            raise ValueError("Unexpected conformance case")
        inputs.append((name, selector, invalid))
    return inputs


def sql_inputs(text):
    # tests/helpers.py applies exactly this filter before both fixture parsers.
    return [line for line in text.splitlines() if line and not line.startswith("--")]


def resource_readers(path, diff, readers, archive):
    if not (path.endswith(".sql") or path == JSON_CASES):
        return readers
    # Non-comment SQL edits usually affect the reader. Avoid loading a fixture
    # unless both sides of every edit consist entirely of ignored lines.
    if path.endswith(".sql") and any(
        line[:1] in {"+", "-"} and not line.startswith(("+++ ", "--- "))
        and line[1:] and not line[1:].startswith("--") for line in diff
    ):
        return readers
    original = archive.read(path).decode("utf-8")
    changed = apply_edit(original, diff)
    if changed is None:
        return readers
    if path.endswith(".sql"):
        return [] if sql_inputs(original) == sql_inputs(changed) else readers
    try:
        if json_inputs(original) == json_inputs(changed):
            return [reader for reader in readers if reader != JSON_READER]
    except (KeyError, TypeError, ValueError, RecursionError):
        pass
    return readers
