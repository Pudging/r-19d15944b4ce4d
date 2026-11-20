"""Blast Radius entry with source-verified comment and fixture selection."""

import json
from pathlib import Path
from zipfile import Path as ZipPath, ZipFile

from scheduler import schedule
from select_paths import select_tests


DATA = Path('/data')
ASSETS = Path(__file__).parent


def main() -> None:
    tests = json.loads((DATA / 'tests.json').read_text(encoding='utf-8'))['tests']
    fixture_index = json.loads((ASSETS / 'fixture_index.json').read_text(encoding='utf-8'))
    all_workers = schedule(tests)
    with ZipFile(ASSETS / 'sqlglot-source.zip') as archive:
        source = ZipPath(archive)
        for patch in sorted((DATA / 'commits').glob('*.patch')):
            try:
                patch_text = patch.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                selected = tests
            else:
                selected = select_tests(patch_text, tests, fixture_index, source)
            workers = all_workers if selected is tests else schedule(selected)
            print(json.dumps({'commit': patch.stem, 'workers': workers}, separators=(',', ':')))


if __name__ == '__main__':
    main()
