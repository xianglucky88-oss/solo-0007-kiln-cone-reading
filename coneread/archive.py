"""Bundle-to-rack archive: candidate racks, per-rack recipe bands, handoffs.

An archive has one bundle per rack: every bundle must be assigned to exactly
one rack and every rack used exactly once.  Bundles carry witness readings
(the same reading model as the original rack report) and a small list of
candidate racks.  Each rack carries its own recipe band.  A handoff ticket is
an extra integer floor/ceiling on one specific ``(bundle, rack)`` pairing, so
it narrows only that pairing's allowed ordinals.
"""
from .intake import parse_archive
from .matching import allowed_edges, hall_deficiency, hopcroft_karp, min_cost_matching
from .ordinal import band_relation, intersect

READING_BOUNDS = {
    'fallen': lambda rank: (rank, None),
    'upright': lambda rank: (0, rank - 1),
    'bending': lambda rank: (rank - 1, rank),
    'unreadable': lambda rank: (0, None),
}


def _readings(rows):
    """Replayable reading evidence: each row and the bound it contributes."""
    evidence = []
    for ticket, reading, cone, rank in rows:
        lower, upper = READING_BOUNDS[reading](rank)
        evidence.append({'ticket': ticket, 'cone': cone, 'reading': reading,
                         'rank': rank, 'lower': lower, 'upper': upper})
    return evidence


def _witness_span(maximum, rows):
    """Intersect the bound of every reading into one closed interval.

    Returns ``(span, conflict)``; ``conflict`` pins the two readings that
    collide when the interval is empty.
    """
    low, high = 0, maximum
    lower_tickets, upper_tickets = [], []
    for ticket, reading, _, rank in rows:
        if reading == 'fallen':
            if rank > low:
                low, lower_tickets = rank, [ticket]
            elif rank == low:
                lower_tickets.append(ticket)
        elif reading == 'upright':
            if rank - 1 < high:
                high, upper_tickets = rank - 1, [ticket]
            elif rank - 1 == high:
                upper_tickets.append(ticket)
        elif reading == 'bending':
            # Bending restricts the ordinal to two adjacent values.
            if rank - 1 > low:
                low, lower_tickets = rank - 1, [ticket]
            elif rank - 1 == low:
                lower_tickets.append(ticket)
            if rank < high:
                high, upper_tickets = rank, [ticket]
            elif rank == high:
                upper_tickets.append(ticket)
    if low > high:
        return None, {'lower_bound': low, 'lower_tickets': sorted(lower_tickets),
                      'upper_bound': high, 'upper_tickets': sorted(upper_tickets)}
    return (low, high), None


def _pair_span(span, tickets):
    """Intersect a witness span with the pairing's handoff intervals."""
    for _, low, high in tickets:
        span = intersect(span, (low, high))
        if span is None:
            return None
    return span


def _replay(rack_names, right_of_left, bundle_names, intervals, racks, prefer_inside):
    """One complete assignment choosing a replayable ordinal for every rack."""
    placements = []
    inside = 0
    for left, right in enumerate(right_of_left):
        rack = rack_names[right]
        low, high = intervals[(bundle_names[left], rack)]
        start, end = racks[rack]
        in_low = max(low, start)
        has_inside = in_low <= min(high, end)
        has_outside = low < start or high > end
        if has_inside and (prefer_inside or not has_outside):
            value, in_band = in_low, True
        else:
            value, in_band = (low if low < start else high), False
        inside += 1 if in_band else 0
        placements.append({'rack': rack, 'bundle': bundle_names[left], 'ordinal': value,
                           'in_band': in_band, 'interval': [low, high]})
    placements.sort(key=lambda item: item['rack'])
    return {'in_band': inside, 'placements': placements}


def _full_report(racks, handoffs, bundle_names, rack_names, intervals,
                 adjacency, match_left, match_right):
    """Report only pairings that take part in at least one complete assignment."""
    usable = sorted(allowed_edges(len(bundle_names), adjacency, match_left, match_right))
    outlook = {rack: {'rack': rack, 'band': list(racks[rack]),
                      'can_be_inside': False, 'can_be_outside': False,
                      'inside_bundles': [], 'outside_bundles': []}
               for rack in rack_names}
    pairings = []
    min_edges, max_edges = [], []
    for left, right in usable:
        bundle, rack = bundle_names[left], rack_names[right]
        low, high = intervals[(bundle, rack)]
        relation = band_relation((low, high), racks[rack])
        batch = handoffs.get((bundle, rack), [])
        pairings.append({'bundle': bundle, 'rack': rack, 'interval': [low, high],
                         'handoff_tickets': [ticket for ticket, _, _ in batch]})
        if relation in ('inside', 'mixed'):
            outlook[rack]['can_be_inside'] = True
            outlook[rack]['inside_bundles'].append(bundle)
        if relation in ('outside', 'mixed'):
            outlook[rack]['can_be_outside'] = True
            outlook[rack]['outside_bundles'].append(bundle)
        # Once a pairing is fixed its in-band choice is independent of every
        # other rack: 'inside' is forced in-band, 'outside' forced out and
        # 'mixed' can go either way.  The two objectives are therefore exactly
        # "avoid in-band racks" and "avoid out-of-band racks".
        min_edges.append((left, right, 1 if relation == 'inside' else 0))
        max_edges.append((left, right, 1 if relation == 'outside' else 0))

    minimum_match = min_cost_matching(len(bundle_names), min_edges)
    maximum_match = min_cost_matching(len(bundle_names), max_edges)
    if minimum_match is None or maximum_match is None:  # pragma: no cover - guarded
        raise ValueError('internal error: allowed pairings do not admit a full assignment')
    minimum = _replay(rack_names, minimum_match, bundle_names, intervals, racks, False)
    maximum = _replay(rack_names, maximum_match, bundle_names, intervals, racks, True)
    return {
        'status': 'full',
        'pairings': pairings,
        'rack_outlook': [outlook[rack] for rack in rack_names],
        'in_band_count': {'minimum': minimum['in_band'], 'maximum': maximum['in_band']},
        'minimum_assignment': minimum,
        'maximum_assignment': maximum,
    }


def _self_contradictions(bundles, bundle_names, witness):
    found = []
    for bundle in bundle_names:
        if witness[bundle]['interval'] is not None:
            continue
        found.append({'bundle': bundle,
                      'readings': witness[bundle]['readings'],
                      'conflict': witness[bundle]['conflict'],
                      'candidate_racks': sorted(bundles[bundle]['candidates'])})
    return found


def _emptied_pairings(handoffs, witness, reasons):
    found = []
    for (bundle, rack), reason in sorted(reasons.items()):
        if reason != 'handoff':
            continue
        base = witness[bundle]['interval']
        found.append({'bundle': bundle, 'rack': rack,
                      'witness_interval': [base[0], base[1]],
                      'readings': witness[bundle]['readings'],
                      'handoffs': [{'ticket': ticket, 'low': low, 'high': high}
                                   for ticket, low, high in handoffs.get((bundle, rack), [])]})
    return found


def _contention(active, adjacency, match_left, match_right, bundle_names, rack_names):
    """Hall-deficiency summary over bundles that still have candidate edges.

    The alternating search is seeded from exactly the active bundles the
    maximum matching left unmatched; the reached bundle set is then Hall
    deficient and every reached rack is genuine supply for it.  That is what
    "each edge is individually usable but they compete for racks" means.
    """
    reached_left, reached_right = hall_deficiency(adjacency, match_left,
                                                  match_right, active)
    deficient = sorted(bundle_names[left] for left in reached_left)
    neighbors = sorted(rack_names[right] for right in reached_right)
    edge_list = [{'bundle': bundle_names[left], 'rack': rack_names[right]}
                 for left in reached_left for right in adjacency[left]
                 if right in set(reached_right)]
    edge_list.sort(key=lambda item: (item['bundle'], item['rack']))
    return {'bundles': deficient, 'racks': neighbors,
            'demand': len(deficient), 'supply': len(neighbors),
            'candidate_edges': edge_list}


def _impossible_report(bundles, handoffs, bundle_names, rack_names, witness,
                       reasons, adjacency, match_left, match_right, bundle_index):
    stranded = [bundle for bundle in bundle_names if not adjacency[bundle_index[bundle]]]
    active = [index for index in range(len(bundle_names)) if adjacency[index]]
    contention = None
    if active and any(match_left[index] == -1 for index in active):
        contention = _contention(active, adjacency, match_left, match_right,
                                 bundle_names, rack_names)
    self_contradiction = _self_contradictions(bundles, bundle_names, witness)
    emptied = _emptied_pairings(handoffs, witness, reasons)
    causes = []
    if self_contradiction:
        causes.append('bundle_self_contradiction')
    if emptied:
        causes.append('handoff_emptied_pairing')
    if contention is not None:
        causes.append('rack_contention')
    return {
        'status': 'impossible',
        'causes': causes,
        'bundle_self_contradiction': self_contradiction,
        'handoff_emptied_pairing': emptied,
        'stranded_bundles': stranded,
        'rack_contention': contention,
    }


def run_archive(document):
    maximum, bundles, racks, handoffs = parse_archive(document)
    bundle_names = sorted(bundles)
    rack_names = sorted(racks)
    bundle_index = {name: index for index, name in enumerate(bundle_names)}
    rack_index = {name: index for index, name in enumerate(rack_names)}

    witness = {}
    for bundle in bundle_names:
        rows = bundles[bundle]['readings']
        span, conflict = _witness_span(maximum, rows)
        witness[bundle] = {'interval': span, 'conflict': conflict,
                           'readings': _readings(rows)}

    intervals = {}
    reasons = {}
    for bundle in bundle_names:
        base = witness[bundle]['interval']
        for rack in sorted(bundles[bundle]['candidates']):
            if base is None:
                reasons[(bundle, rack)] = 'bundle'
                continue
            span = _pair_span(base, handoffs.get((bundle, rack), []))
            if span is None:
                reasons[(bundle, rack)] = 'handoff'
            else:
                intervals[(bundle, rack)] = span

    adjacency = {index: [] for index in range(len(bundle_names))}
    for bundle, rack in intervals:
        adjacency[bundle_index[bundle]].append(rack_index[rack])
    for index in adjacency:
        adjacency[index].sort()

    match_left, match_right = hopcroft_karp(len(bundle_names), adjacency)
    if all(right != -1 for right in match_left):
        return _full_report(racks, handoffs, bundle_names, rack_names,
                            intervals, adjacency, match_left, match_right)
    return _impossible_report(bundles, handoffs, bundle_names, rack_names,
                              witness, reasons, adjacency,
                              match_left, match_right, bundle_index)
