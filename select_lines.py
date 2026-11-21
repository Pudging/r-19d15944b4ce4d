"""Select pinned per-test line coverage for changes to executable expressions."""
import ast
from functools import lru_cache

from select_scopes import apply_edit


# Each field is evaluated only when the statement reaches this expression.
EXPRESSION_FIELDS = {
    ast.Return: ("value",), ast.Assign: ("value",), ast.AnnAssign: ("value",),
    ast.Expr: ("value",), ast.Raise: ("exc", "cause"), ast.Assert: ("test", "msg"),
    ast.If: ("test",), ast.While: ("test",), ast.For: ("iter",), ast.AsyncFor: ("iter",),
}
BINDERS = (ast.NamedExpr, ast.Yield, ast.YieldFrom, ast.Await, ast.Lambda,
           ast.GeneratorExp, ast.ListComp, ast.DictComp, ast.SetComp)


def expression_changes(before, after):
    """Require identical module shape outside runtime expressions in function bodies."""
    changes = []

    def visit(left, right, inside=False):
        if type(left) is not type(right):
            return False
        if isinstance(left, list):
            return len(left) == len(right) and all(visit(a,b,inside) for a,b in zip(left,right))
        if not isinstance(left, ast.AST):
            return left == right
        expr_fields = EXPRESSION_FIELDS.get(type(left), ()) if inside else ()
        for field, value in ast.iter_fields(left):
            new = getattr(right, field)
            if field in expr_fields and isinstance(value, ast.expr) and isinstance(new, ast.expr):
                if ast.dump(value) != ast.dump(new):
                    if any(isinstance(n, BINDERS) for e in (value, new) for n in ast.walk(e)):
                        return False
                    # Include the leading statement line too: coverage may attribute a
                    # multiline value or a short-circuiting expression to its first line.
                    changes.append((left.lineno, value.end_lineno))
                continue
            nested = inside
            if isinstance(left, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nested = field == "body"
            elif isinstance(left, ast.ClassDef):
                nested = False
            if not visit(value, new, nested):
                return False
        return True

    return changes if visit(before, after) and changes else None


@lru_cache(maxsize=32)
def parse_original(original):
    return ast.parse(original, type_comments=True)


def affected_lines(path, diff, source, line_map):
    if path not in line_map["coverage"] or not (source / path).is_file():
        return None
    original = (source / path).read_text(encoding="utf-8")
    updated = apply_edit(original, diff)
    if updated is None:
        return None
    try:
        compile(updated, path, "exec")
        spans = expression_changes(parse_original(original), ast.parse(updated, type_comments=True))
    except (SyntaxError, ValueError, RecursionError):
        return None
    if not spans:
        return None
    mask = 0
    for start, end in spans:
        mask |= ((1 << (end-start+1))-1) << start
    by_context = line_map["coverage"][path]
    matched = {line_map["tests"][int(i)] for i, bits in by_context.items() if int(bits,16) & mask}
    if "" in matched:
        return None
    return matched
