"""Recognize narrow value replacements in built-in dialect class attributes."""

import ast
import re

from select_scopes import apply_edit, changed_body_spans


DIALECT_MODULE = re.compile(r"sqlglot/(dialects|parsers|generators|tokens)/([a-z][a-z0-9_]*)\.py")
COMPONENTS = {"Tokenizer", "Parser", "Generator", "JSONPathTokenizer"}
SCALAR_TYPES = (str, bytes, int, float, bool)


def equal_ast(before, after):
    return ast.dump(before) == ast.dump(after)


def same_literal_shape(before, after):
    if type(before) is not type(after):
        return False
    if isinstance(before, ast.Constant):
        return type(before.value) is type(after.value) and (
            before.value == after.value or type(before.value) in SCALAR_TYPES
        )
    if isinstance(before, ast.Dict):
        # Keys carry dispatch identity. A changed key can impact more than its old readers.
        return (
            len(before.keys) == len(after.keys)
            and all(
                (left is None and right is None)
                or (left is not None and right is not None and equal_ast(left, right))
                for left, right in zip(before.keys, after.keys)
            )
            and same_literal_shape(before.values, after.values)
        )
    if isinstance(before, ast.AST):
        return all(
            same_literal_shape(value, getattr(after, field))
            for field, value in ast.iter_fields(before)
        )
    if isinstance(before, list):
        return len(before) == len(after) and all(
            same_literal_shape(left, right) for left, right in zip(before, after)
        )
    return before == after


def target_name(statement):
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]
    elif isinstance(statement, ast.AnnAssign):
        target = statement.target
    else:
        return None
    return target.id if isinstance(target, ast.Name) and target.id.isupper() else None


def same_component(before, after, *, outer):
    if not isinstance(before, ast.ClassDef) or not isinstance(after, ast.ClassDef):
        return False
    if before.name != after.name or before.decorator_list or after.decorator_list:
        return False
    if not outer and before.name not in COMPONENTS:
        return False
    if not outside_body_unchanged(before, after) or len(before.body) != len(after.body):
        return False
    for left, right in zip(before.body, after.body):
        if equal_ast(left, right):
            continue
        if same_component(left, right, outer=False):
            continue
        if not same_assignment(left, right):
            return False
    return True


def same_assignment(before, after):
    if type(before) is not type(after):
        return False
    name = target_name(before)
    if name is None or name != target_name(after):
        return False
    if isinstance(before, ast.AnnAssign) and not equal_ast(before.annotation, after.annotation):
        return False
    if getattr(before, "type_comment", None) != getattr(after, "type_comment", None):
        return False
    return same_literal_shape(before.value, after.value)


def outside_body_unchanged(before, after):
    for field, value in ast.iter_fields(before):
        if field == "body":
            continue
        if not same_literal_shape(value, getattr(after, field)):
            return False
        # Class headers must be identical, including literals in generic bases.
        if isinstance(value, list) and not all(
            equal_ast(left, right) for left, right in zip(value, getattr(after, field))
        ):
            return False
    return True


def get_module_change(path, diff, source):
    match = DIALECT_MODULE.fullmatch(path)
    if not match or match[2] == "dialect" or not (source / path).is_file():
        return None
    original = (source / path).read_text(encoding="utf-8")
    changed = apply_edit(original, diff)
    if changed is None:
        return None
    return original, changed


def localized_class_values(path, diff, source):
    change = get_module_change(path, diff, source)
    if change is None:
        return False
    original, changed = change
    try:
        compile(changed, path, "exec")
        before = ast.parse(original, type_comments=True)
        after = ast.parse(changed, type_comments=True)
    except (SyntaxError, ValueError, RecursionError):
        return False
    if len(before.body) != len(after.body) or not outside_body_unchanged(before, after):
        return False
    changed_statements = [
        (left, right) for left, right in zip(before.body, after.body)
        if not equal_ast(left, right)
    ]
    return bool(changed_statements) and all(
        same_component(left, right, outer=True) for left, right in changed_statements
    )


def localized_function_values(path, diff, source):
    change = get_module_change(path, diff, source)
    return change is not None and changed_body_spans(*change) is not None
