"""Narrow changes by observable pre-change comparisons, constructors and attribute readers."""
import ast

from select_scopes import apply_edit

PAIRED = {"is": "==", "==": "is", "is not": "!=", "!=": "is not"}
SINGLETONS = {"builtins.NoneType", "builtins.bool", "builtins.NotImplementedType", "builtins.ellipsis"}


def identity_semantics(left, right, observed, negative):
    """Whether these two exact runtime types compare by identity for all instances."""
    lt, rt = observed["types"][left], observed["types"][right]
    slot = 2 if negative else 1
    if left == right and lt[0] in observed["string_enums"]:
        return True
    def identity_type(t):
        return (t[1] and t[slot]) or t[0] in SINGLETONS - {"builtins.bool"}
    if identity_type(lt) and identity_type(rt):
        return True
    # None and bool are immutable singleton values of their respective types.
    if lt[0] in SINGLETONS and rt[0] in SINGLETONS:
        return True
    return False


def byte_change(before, after, start, stop):
    left, right = before.encode(), after.encode()
    tail = len(left) - stop
    if len(right) < start + tail or left[:start] != right[:start]:
        return None
    if tail and left[stop:] != right[-tail:]:
        return None
    return left[start:stop].decode(), right[start:len(right)-tail].decode()


def observe_site(path, kind, key, old, new, data):
    if kind == "compare":
        previous, changed = old.strip(), new.strip()
        # Keep token separation. In particular, 'x is y' cannot become 'xisy'.
        if previous not in PAIRED or changed != PAIRED[previous]:
            return None
        if changed.startswith("is") and (new == new.lstrip() or new == new.rstrip()):
            return None
        groups = data["comparisons"].get(path, {}).get(key)
        if not groups:
            return None
        risky = set()
        for left, right, ids in groups:
            if not left or not right or any(
                not identity_semantics(a,b,data,previous in ("is not","!=")) for a in left for b in right
            ):
                risky.update(ids)
        return risky
    try:
        before_text, after_text = old.strip(), new.strip()
        before = ast.parse(before_text, mode="eval").body
        after = ast.parse(after_text, mode="eval").body
        if not isinstance(before, ast.Constant) or not isinstance(after, ast.Constant):
            return None
        if ast.get_source_segment(after_text, after) != after_text:
            return None
        old_value, new_value = before.value, after.value
    except (SyntaxError,ValueError):
        return None
    if type(old_value) is not type(new_value):
        return None
    if kind == "class" and type(new_value) is bool:
        if key not in data["classes"]:
            return None
        names = ("arg_types","required_args",key.rsplit(".",1)[-1])
        return set(data["classes"][key]) | {i for n in names for i in data["source_readers"].get(n, ())}
    if kind == "attribute" and key in data["attributes"]:
        return set(data["attributes"][key]) | set(data["source_readers"].get(key, ()))
    return None


def affected_observations(path, diff, source, data):
    table = data["locations"].get(path)
    if not table:
        return None
    original = (source / path).read_text(encoding="utf-8")
    updated = apply_edit(original, diff)
    if updated is None:
        return None
    old_lines, new_lines = original.splitlines(), updated.splitlines()
    if len(old_lines) != len(new_lines):
        return None
    matches = set()
    changed = False
    for lineno, (left,right) in enumerate(zip(old_lines,new_lines),1):
        if left == right:
            continue
        changed = True
        for start,stop,kind,key in table.get(str(lineno), ()):
            pair = byte_change(left,right,start,stop)
            if pair is None:
                continue
            observation = observe_site(path,kind,key,*pair,data)
            if observation is not None:
                matches.update(observation)
                break
        else:
            return None
    if not changed:
        return None
    try:
        compile(updated,path,"exec")
    except (SyntaxError,ValueError):
        return None
    tests = data["tests"]
    if tests.index("") in matches:
        return None
    return {tests[i] for i in matches}
