import argparse
import json
from pathlib import Path
import sys

from .pipeline import run


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description='ordinal endpoints, witness preservation, and contradictory evidence')
    parser.add_argument('input', type=Path, help='source JSON document or saved report with an archive snapshot')
    parser.add_argument('amendments', type=Path, nargs='?',
                        help='optional batch of corrections and retractions applied to a saved archive')
    args = parser.parse_args()
    try:
        payload = _read(args.input)
        if args.amendments is not None:
            if not isinstance(payload, dict):
                raise ValueError('archive must be an object')
            payload = dict(payload)
            if 'archive' not in payload and payload.get('version') != 2:
                raise ValueError('archive snapshot missing')
            payload['amendments'] = _read(args.amendments)
        report = run(payload)
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        print(f'input rejected: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
