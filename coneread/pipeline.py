"""Report orchestration: dispatch the legacy rack report or the archive report."""
from .archive import run_archive
from .intake import BUNDLE_KEYS, parse_legacy
from .ordinal import classify, estimate


def _legacy(document):
    maximum, band, racks = parse_legacy(document)
    reports = []
    for name, witnesses in sorted(racks.items()):
        low, high, evidence = estimate(maximum, witnesses)
        reports.append({'rack': name, 'interval': [low, high] if low <= high else None,
                        'status': classify(low, high, band), 'evidence': evidence})
    return {'target_band': band, 'racks': reports}


def run(document):
    if isinstance(document, dict) and any(key in document for key in BUNDLE_KEYS):
        return run_archive(document)
    return _legacy(document)
