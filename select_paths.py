"""Conservative fixture selection with a full-suite fallback for code changes."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import PurePosixPath
from zipfile import Path


DIFF_HEADER = re.compile(r'diff --git a/([^\s]+) b/([^\s]+)')
HUNK_HEADER = re.compile(r'@@ -([0-9]{1,9})(?:,([0-9]{1,9}))? \+([0-9]{1,9})(?:,([0-9]{1,9}))? @@(?: .*)?')
INDEX_HEADER = re.compile(r'index [0-9a-f]+\.\.[0-9a-f]+(?: [0-7]{6})?')
ORDINARY_COMMENT = re.compile(r'[ \t]*# (?!type:|coding[:=]|fmt:|noqa\b|pragma:).+$')


def file_edits(patch: str) -> dict[str, list[str]] | None:
    edits = {}
    current = None
    for line in patch.removesuffix('\n').split('\n'):
        if line.startswith('diff --git '):
            match = DIFF_HEADER.fullmatch(line)
            if not match or match[1] != match[2] or match[1] in edits:
                return None
            current = []
            edits[match[1]] = current
        elif current is None:
            return None
        else:
            current.append(line)
    if not edits or not all(valid_text_edit(path, lines) for path, lines in edits.items()):
        return None
    return edits


def valid_text_edit(path: str, lines: list[str]) -> bool:
    start = int(bool(lines and INDEX_HEADER.fullmatch(lines[0])))
    if lines[start:start + 2] != [f'--- a/{path}', f'+++ b/{path}']:
        return False
    old_left = new_left = 0
    saw_hunk = False
    for line in lines[start + 2:]:
        if match := HUNK_HEADER.fullmatch(line):
            if old_left or new_left:
                return False
            old_left, new_left = int(match[2] or '1'), int(match[4] or '1')
            saw_hunk = True
            continue
        prefix = line[:1]
        if not saw_hunk or prefix not in (' ', '-', '+'):
            return False
        old_left -= prefix != '+'
        new_left -= prefix != '-'
        if min(old_left, new_left) < 0:
            return False
    return saw_hunk and old_left == new_left == 0


def comment_only(path: Path, diff: list[str]) -> bool:
    """Prove that every added line tokenizes as a comment in context."""
    if not path.is_file() or path.suffix != '.py':
        return False
    original = path.read_text(encoding='utf-8')
    old_lines = original.removesuffix('\n').split('\n')
    rebuilt = []
    added_lines = []
    pos = 0
    old_remaining = new_remaining = None
    for line in diff:
        if line.startswith('@@'):
            match = HUNK_HEADER.fullmatch(line)
            if not match or old_remaining or new_remaining:
                return False
            old_remaining = int(match[2] or '1')
            new_remaining = int(match[4] or '1')
            start = int(match[1]) - bool(old_remaining)
            if start < pos or start > len(old_lines):
                return False
            rebuilt.extend(old_lines[pos:start])
            pos = start
            if int(match[3]) - bool(new_remaining) != len(rebuilt):
                return False
        elif old_remaining is None:
            if not line.startswith(('index ', '--- a/', '+++ b/')):
                return False
        elif (
            old_remaining and new_remaining and line.startswith(' ')
            and pos < len(old_lines) and old_lines[pos] == line[1:]
        ):
            rebuilt.append(line[1:])
            pos += 1
            old_remaining -= 1
            new_remaining -= 1
        elif new_remaining and line.startswith('+') and ORDINARY_COMMENT.fullmatch(line[1:]):
            rebuilt.append(line[1:])
            added_lines.append(len(rebuilt))
            new_remaining -= 1
        else:
            return False
    if not added_lines or old_remaining or new_remaining:
        return False
    rebuilt.extend(old_lines[pos:])
    modified = '\n'.join(rebuilt) + '\n'
    try:
        original_encoding, _ = tokenize.detect_encoding(io.BytesIO(original.encode('utf-8')).readline)
        updated_encoding, _ = tokenize.detect_encoding(io.BytesIO(modified.encode('utf-8')).readline)
        if original_encoding != updated_encoding:
            return False
        comments = {
            item.start[0] for item in tokenize.generate_tokens(io.StringIO(modified).readline)
            if item.type == tokenize.COMMENT
        }
        return all(line in comments for line in added_lines) and ast.dump(
            ast.parse(original, type_comments=True)
        ) == ast.dump(ast.parse(modified, type_comments=True))
    except (SyntaxError, tokenize.TokenError):
        return False


def fixture_tests(readers: set[str], tests: list[dict]) -> list[dict] | None:
    """Resolve pinned reader names to scorer catalogue entries."""
    selected = []
    matched = set()
    for test in tests:
        names = {test['file'], f"{test['file']}::{test['id'].split('::')[-1].split('[')[0]}"}
        if hits := readers & names:
            selected.append(test)
            matched.update(hits)
    return selected if matched == readers else None


def select_tests(
    patch: str, tests: list[dict], index: dict[str, list[str]], source: Path | None = None,
) -> list[dict]:
    edits = file_edits(patch)
    if edits is None:
        return tests
    readers = set()
    for path, lines in edits.items():
        if path in index:
            readers.update(index[path])
        elif (
            source is not None and path.startswith('sqlglot/')
            and '..' not in PurePosixPath(path).parts and comment_only(source / path, lines)
        ):
            continue
        else:
            return tests
    selected = fixture_tests(readers, tests)
    return tests if selected is None else selected
