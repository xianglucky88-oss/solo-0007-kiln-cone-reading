"""CLI entry for catalog migration and archivist correction reports.

    python3 -B -m coneread.migration OLD_DOC MIGRATION_SPEC [CORRECTION]

The old document is consumed through the unchanged historical input contract.
With two arguments a formal migration report is emitted; with three, an
incremental correction report checked against a full corrected-catalog replay.
"""

import argparse
import json
from pathlib import Path
import sys

from . import MigrationState
from .corrections import apply_correction


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='cone catalog migration with explicit mapping and correction replay')
    parser.add_argument('old_document', type=Path, help='historical input document (unchanged contract)')
    parser.add_argument('migration_spec', type=Path, help='new catalog and explicit old->new mapping')
    parser.add_argument('correction', nargs='?', type=Path,
                        help='optional single archivist correction document')
    args = parser.parse_args(argv)
    try:
        old_document = _load(args.old_document)
        spec = _load(args.migration_spec)
        state = MigrationState(old_document, spec)
        if args.correction is None:
            report = state.formal_report()
        else:
            correction = _load(args.correction)
            report = apply_correction(state, correction, old_document)
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        print(f'input rejected: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
