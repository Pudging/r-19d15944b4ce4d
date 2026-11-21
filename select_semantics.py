"""Refine pinned source dependencies with traced dispatch and primitive comparisons."""
import ast
import hashlib
import operator

from select_lines import affected_lines
from select_observed import byte_change
from select_scopes import apply_edit

OPERATIONS = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
              ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}

def primitive_literal(node):
    if isinstance(node, ast.Constant) and (type(node.value) in (int,str,bool) or node.value is None):
        return True
    return isinstance(node, ast.Tuple) and all(isinstance(v, ast.Constant) and type(v.value) is int for v in node.elts)

def comparison(text):
    node = ast.parse(text.strip(), mode="eval").body
    if not isinstance(node,ast.Compare) or len(node.ops)!=1 or type(node.ops[0]) not in OPERATIONS:
        return None
    left,right = node.left,node.comparators[0]
    side = primitive_literal(left)
    if side == primitive_literal(right):
        return None
    literal = ast.literal_eval(left if side else right)
    return ast.dump(right if side else left),side,type(node.ops[0]),literal

def unchanged(value, before, after):
    tag, operand = value
    _, left, old_op, old_lit = before
    _, _, new_op, new_lit = after
    if tag=="?":
        return False
    if tag=="s":
        if old_op not in (ast.Eq,ast.NotEq) or new_op not in (ast.Eq,ast.NotEq):
            return False
        if type(old_lit) is not str or type(new_lit) is not str:
            return False
        old_lit = hashlib.sha256(old_lit.encode()).hexdigest()
        new_lit = hashlib.sha256(new_lit.encode()).hexdigest()
    elif tag=="t":
        operand=tuple(operand)
    try:
        old_result=OPERATIONS[old_op](old_lit,operand) if left else OPERATIONS[old_op](operand,old_lit)
        new_result=OPERATIONS[new_op](new_lit,operand) if left else OPERATIONS[new_op](operand,new_lit)
        return old_result == new_result
    except TypeError:
        return False

def refine(path,diff,source,selected,lines,data):
    table=data["locations"].get(path)
    if not table or not selected:
        return selected
    original=(source/path).read_text(encoding="utf-8")
    updated=apply_edit(original,diff)
    if updated is None:
        return selected
    old=original.splitlines()
    new=updated.splitlines()
    if len(old)!=len(new):
        return selected
    changed=[(i,a,b) for i,(a,b) in enumerate(zip(old,new),1) if a!=b]
    if len(changed)!=1:
        return selected
    line,a,b=changed[0]
    for start,end,kind,key in table.get(str(line),()):
        pair=byte_change(a,b,start,end)
        if pair is None:
            continue
        try:
            if kind=="lambda":
                first,last=[ast.parse(s.strip(),mode="eval").body for s in pair]
                if not all(isinstance(node,ast.Constant) and ast.get_source_segment(s.strip(),node)==s.strip()
                           for s,node in zip(pair,(first,last))) or type(first.value) is not type(last.value):
                    continue
                keep=set(data["records"][key])
            else:
                previous,modified=map(comparison,pair)
                if not previous or not modified or previous[:2]!=modified[:2] or type(previous[3]) is not type(modified[3]):
                    continue
                keep=set()
                witnessed=set()
                for observed,ids in data["records"][key]:
                    witnessed.update(ids)
                    if any(not unchanged(value,previous,modified) for value in observed):
                        keep.update(ids)
                # Independent Python line hits without a primitive probe stay scheduled.
                mask=1<<line
                missing={lines["tests"][int(i)] for i,bits in lines["coverage"].get(path,{}).items() if int(bits,16)&mask}
                missing.difference_update(data["ids"][i] for i in witnessed)
                if "" in missing:
                    continue
            compile(updated,path,"exec")
        except (SyntaxError, ValueError, OverflowError):
            continue
        ids={data["ids"][i] for i in keep}
        ids.update(data["unverified"])
        if kind=="compare":
            ids.update(missing)
        return [t for t in selected if t["id"] in ids]
    return selected

def child_guards(path,diff,source,guards,data):
    """Only resolve inherited subprocess guards for source edits already localized."""
    still_needed=set(guards)
    for test,paths in data["children"].items():
        if test not in still_needed:
            continue
        if path not in paths:
            still_needed.discard(test)
            continue
        child_lines={"tests":[test],"coverage":{path:{"0":paths[path]}}}
        if affected_lines(path,diff,source,child_lines)==set():
            still_needed.discard(test)
    return still_needed
