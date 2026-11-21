"""Use pinned per-test coverage only for proven, localized function-body edits."""

import ast

from select_paths import HUNK_HEADER


def apply_edit(original, diff):
    lines = original.removesuffix("\n").split("\n")
    output = []
    cursor = 0
    in_hunk = False
    for line in diff:
        if match := HUNK_HEADER.fullmatch(line):
            start = int(match[1]) - bool(int(match[2] or "1"))
            if not cursor <= start <= len(lines):
                return None
            output.extend(lines[cursor:start])
            cursor = start
            if int(match[3]) - bool(int(match[4] or "1")) != len(output):
                return None
            in_hunk = True
        elif in_hunk:
            prefix, content = line[0], line[1:]
            if prefix != "+":
                if cursor == len(lines) or lines[cursor] != content:
                    return None
                cursor += 1
            if prefix != "-":
                output.append(content)
    output.extend(lines[cursor:])
    return "\n".join(output) + "\n"


class Outline(ast.NodeTransformer):
    def __init__(self):
        self.bodies = []

    def visit_FunctionDef(self, node):
        body = node.body
        prefix = []
        if ast.get_docstring(node, clean=False) is not None:
            prefix, body = body[:1], body[1:]
        start = body[0].lineno if body else node.end_lineno
        self.bodies.append((start, node.end_lineno, tuple(ast.dump(stmt) for stmt in body)))
        node.body = [*prefix, ast.Pass()]
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


def changed_body_spans(original, updated):
    previous = Outline()
    current = Outline()
    try:
        compile(updated, "<patched module>", "exec")
        before = previous.visit(ast.parse(original, type_comments=True))
        after = current.visit(ast.parse(updated, type_comments=True))
    except (SyntaxError, ValueError, RecursionError):
        return None
    if ast.dump(before) != ast.dump(after):
        return None
    changed = [
        (start, end)
        for (start, end, left), (_, _, right) in zip(previous.bodies, current.bodies)
        if left != right
    ]
    return changed or None


def affected_ids(path, diff, source, scopes):
    if path not in scopes or not (source / path).is_file():
        return None
    original = (source / path).read_text(encoding="utf-8")
    updated = apply_edit(original, diff)
    if updated is None:
        return None
    spans = changed_body_spans(original, updated)
    if spans is None:
        return None
    by_span = {(start, end): ids for start, end, ids in scopes[path]}
    if any(span not in by_span for span in spans):
        return None
    return {test for span in spans for test in by_span[span]}
