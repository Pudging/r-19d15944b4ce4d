"""Qualify pinned declaration edits against observed callbacks, calls and name readers."""
import ast
from functools import lru_cache
import gzip
import json
from pathlib import Path

from select_scopes import apply_edit

ATOMS = (int, float, bool, str, bytes)
LITERALS = (ast.Constant, ast.Dict, ast.Tuple, ast.List, ast.Set, ast.Load, ast.UnaryOp, ast.USub, ast.UAdd)

@lru_cache(maxsize=1)
def load_declarations():
    with gzip.open(Path(__file__).with_name("declarations.json.gz"), "rt", encoding="utf-8") as stream:
        data = json.load(stream)
    return data

def compatible(left, right, kind):
    if kind in ("default", "factory"):
        return (isinstance(left, ast.Constant) and isinstance(right, ast.Constant)
                and type(left.value) in ATOMS and type(left.value) is type(right.value))
    if kind == "constant":
        if any(not isinstance(node, LITERALS) for tree in (left, right) for node in ast.walk(tree)):
            return False
        try:
            return type(ast.literal_eval(left)) is type(ast.literal_eval(right))
        except (TypeError, ValueError, SyntaxError):
            return False
    # Keep names, scoping, binding and the shape of the expression identical.
    # Only ordinary attribute names and same-type immutable literals may vary.
    def same(a, b):
        if type(a) is not type(b):
            return False
        if isinstance(a, ast.Constant):
            return type(a.value) is type(b.value)
        if isinstance(a, ast.Attribute):
            return (a.attr == b.attr or not (a.attr.startswith("__") or b.attr.startswith("__"))) and same(a.value, b.value)
        if isinstance(a, ast.AST):
            return all(same(value, getattr(b, field)) for field, value in ast.iter_fields(a))
        if isinstance(a, list):
            return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
        return a == b
    return same(left, right)

def changed_rows(diff):
    """Deleted line coordinates provide a cheap prefilter before opening source."""
    from select_paths import HUNK_HEADER
    row = None
    result = set()
    for line in diff:
        if line.startswith("@@"):
            match = HUNK_HEADER.fullmatch(line)
            if match is None:
                return set()
            row = int(match[1])
        elif row is not None:
            if line.startswith("-"):
                result.add(row)
            if not line.startswith("+"):
                row += 1
    return result

def projected(path, diff, source, data):
    sites = data["paths"].get(path)
    if not sites:
        return None
    rows = changed_rows(diff)
    if not rows:
        return None
    regions = {tuple(site) for site in sites if any(site[0] <= line <= site[2] for line in rows)}
    if not regions or not all(any(s[0] <= line <= s[2] for s in regions) for line in rows):
        return None
    original = (source / path).read_text(encoding="utf-8")
    updated = apply_edit(original, diff)
    if updated is None:
        return None
    old, new = original.splitlines(), updated.splitlines()
    if len(old) != len(new):
        return None
    changed = {i for i, (before, after) in enumerate(zip(old, new), 1) if before != after}
    if not changed or not changed <= rows:
        return None
    chosen = set()
    for row in changed:
        before, after = old[row - 1].encode(), new[row - 1].encode()
        for reg in sorted(regions):
            start, col, stop, end = reg[:4]
            if not start <= row <= stop:
                continue
            left = col if row == start else 0
            tail = len(before) - end if row == stop else 0
            if (len(after) >= left + tail and before[:left] == after[:left]
                    and (not tail or before[-tail:] == after[-tail:])):
                chosen.add(reg)
                break
        else:
            return None
    try:
        compile(updated, path, "exec")
        trees = [ast.parse(text, type_comments=True) for text in (original, updated)]
    except (SyntaxError, ValueError, RecursionError):
        return None
    nodes = [{(n.lineno, n.col_offset, n.end_lineno, n.end_col_offset): n
              for n in ast.walk(tree) if isinstance(n, ast.expr)} for tree in trees]
    ids = set()
    for start, col, stop, end, kind, key, _ in chosen:
        offset = len(new[stop-1].encode()) - len(old[stop-1].encode())
        left = nodes[0].get((start, col, stop, end))
        right = nodes[1].get((start, col, stop, end + offset))
        if left is None or right is None or not compatible(left, right, kind):
            return None
        ids.update(data["ids"][i] for i in data["sets"][key])
    return ids
