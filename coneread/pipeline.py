from .intake import parse
from .ordinal import classify, estimate


def run(document):
    maximum, band, racks = parse(document)
    reports = []
    for name, witnesses in sorted(racks.items()):
        low, high, evidence = estimate(maximum, witnesses)
        reports.append({'rack': name, 'interval': [low, high] if low <= high else None,
                        'status': classify(low, high, band), 'evidence': evidence})
    return {'target_band': band, 'racks': reports}
