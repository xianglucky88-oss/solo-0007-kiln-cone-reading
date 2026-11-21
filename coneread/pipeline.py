from .intake import (apply_amendments, is_v2_document, parse, parse_amendments,
                     parse_archive, parse_v2)
from .ordinal import archive_estimate, classify, estimate

AMENDMENT_KEYS = ('amendments', 'corrections', 'retractions')


def _legacy(document):
    """Original single-ticket-per-cone report; output shape stays byte-identical."""
    maximum, band, racks = parse(document)
    reports = []
    for name, witnesses in sorted(racks.items()):
        low, high, evidence = estimate(maximum, witnesses)
        reports.append({'rack': name, 'interval': [low, high] if low <= high else None,
                        'status': classify(low, high, band), 'evidence': evidence})
    return {'target_band': band, 'racks': reports}


def _witness_rows(rack):
    catalog = rack['_catalog']
    return [(row['ticket'], row['reading'], catalog[row['cone']])
            for row in rack['witnesses']]


def _attach_catalog(state):
    """Keep the cone lookup next to each rack without leaking bookkeeping into snapshots."""
    return [dict(rack, _catalog=state['cone_ranks']) for rack in state['racks']]


def _snapshot(state):
    """The archive: everything needed to keep checking without the original capture file."""
    return {'version': 2, 'rank_ceiling': state['rank_ceiling'],
            'band': list(state['band']), 'cone_ranks': dict(state['cone_ranks']),
            'budget': state['budget'],
            'racks': [{'id': rack['id'], 'budget': rack['budget'],
                       'witnesses': [dict(row) for row in rack['witnesses']]}
                      for rack in state['racks']]}


def _analyze(state, rack):
    return archive_estimate(state['rank_ceiling'], state['band'],
                            rack['budget'], _witness_rows(rack))


def _rack_report(rack, analysis, changes=None):
    report = {'rack': rack['id'], 'budget': rack['budget'],
              'interval': analysis['segments'][0]['interval'] if len(analysis['segments']) == 1 else None,
              'status': analysis['status'],
              'segments': analysis['segments'],
              'unreadable': analysis['unreadable']}
    if changes is not None:
        report['changes'] = changes
    return report


def _intervals(analysis):
    return [tuple(segment['interval']) for segment in analysis['segments']]


def _values(ranges):
    return {value for low, high in ranges for value in range(low, high + 1)}


def _difference(left, right):
    """Value-level inclusive ranges: ranks in `left` but not in `right`."""
    absent = sorted(_values(left) - _values(right))
    result = []
    for value in absent:
        if result and result[-1][1] == value - 1:
            result[-1][1] = value
        else:
            result.append([value, value])
    return result


def _evidence_delta(before, after):
    delta = {}
    for field in ('support', 'conflicts', 'blocking'):
        old = set(before[field])
        new = set(after[field])
        added = sorted(new - old)
        removed = sorted(old - new)
        if added or removed:
            delta[field] = {'added': added, 'removed': removed}
    return delta


def _compare(old, new):
    old_intervals = _intervals(old)
    new_intervals = _intervals(new)
    added = _difference(new_intervals, old_intervals)
    removed = _difference(old_intervals, new_intervals)
    old_segments = {tuple(s['interval']): s for s in old['segments']}
    new_segments = {tuple(s['interval']): s for s in new['segments']}
    evidence = []
    for interval in sorted(set(new_intervals) & set(old_intervals)):
        for end in ('minimum', 'maximum'):
            delta = _evidence_delta(old_segments[interval]['evidence'][end],
                                    new_segments[interval]['evidence'][end])
            if delta:
                evidence.append({'interval': list(interval), 'end': end, **delta})
    unreadable = {'added': sorted(set(new['unreadable']) - set(old['unreadable'])),
                  'removed': sorted(set(old['unreadable']) - set(new['unreadable']))}
    status = {'from': old['status'], 'to': new['status']}
    changes = {'added_intervals': added, 'removed_intervals': removed,
               'status': status, 'evidence_changed': evidence}
    if unreadable['added'] or unreadable['removed']:
        changes['unreadable'] = unreadable
    changes['unchanged'] = not (added or removed or evidence
                                or status['from'] != status['to']
                                or unreadable['added'] or unreadable['removed'])
    return changes


def _archive(document):
    state = parse_v2(document)
    racks = _attach_catalog(state)
    reports = [_rack_report(rack, _analyze(state, rack)) for rack in racks]
    return {'mode': 'archive', 'target_band': state['band'], 'budget': state['budget'],
            'racks': reports, 'archive': _snapshot(state)}


def _amendment_source(document):
    if 'amendments' in document:
        return document['amendments']
    return {key: document[key] for key in ('corrections', 'retractions') if key in document}


def _owns(state, rack_name, ticket):
    for rack in state['racks']:
        if rack['id'] == rack_name:
            return any(row['ticket'] == ticket for row in rack['witnesses'])
    return False


def _recompute(document):
    """Apply a batch of corrections/retractions to a stored archive.

    Only racks named by the batch are re-analyzed; every other rack is merely
    carried forward in the refreshed snapshot.
    """
    state = parse_archive(document)
    corrections, retractions = parse_amendments(_amendment_source(document))
    updated, touched = apply_amendments(state, corrections, retractions)
    old_racks = {rack['id']: rack for rack in _attach_catalog(state)}
    new_racks = {rack['id']: rack for rack in _attach_catalog(updated)}
    reports = []
    for name in touched:
        old = _analyze(state, old_racks[name])
        new = _analyze(updated, new_racks[name])
        changes = _compare(old, new)
        changes['amended'] = {'corrected': sorted(t for t in corrections
                                                  if _owns(state, name, t)),
                              'retracted': sorted(t for t in retractions
                                                  if _owns(state, name, t))}
        reports.append(_rack_report(new_racks[name], new, changes))
    return {'mode': 'recompute', 'target_band': updated['band'],
            'budget': updated['budget'], 'touched': list(touched),
            'untouched': sorted(set(new_racks) - set(touched)),
            'racks': reports, 'archive': _snapshot(updated)}


def run(document):
    """Dispatch on document shape; the legacy single-ticket path is unchanged."""
    if isinstance(document, dict) and 'archive' in document:
        return _recompute(document)
    amended = isinstance(document, dict) and any(key in document for key in AMENDMENT_KEYS)
    if is_v2_document(document):
        return _recompute(document) if amended else _archive(document)
    if amended:
        raise ValueError('archive snapshot missing')
    return _legacy(document)
