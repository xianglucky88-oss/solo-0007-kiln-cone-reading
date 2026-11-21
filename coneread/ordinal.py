"""Ordinal semantics.

Two modes share this module:

* :func:`estimate` reproduces the original single-ticket-per-cone rule exactly.
* :func:`archive_estimate` implements the multi-ticket archive rule where a
  rack may discard up to ``budget`` readable tickets.  Unreadable tickets never
  constrain a value and never spend budget.
"""

READINGS = ('fallen', 'upright', 'bending', 'unreadable')
READABLE = frozenset(('fallen', 'upright', 'bending'))


def bounds(maximum, rank, reading):
    return {
        'fallen': (rank, maximum),
        'upright': (0, rank - 1),
        'bending': (rank - 1, rank),
        'unreadable': (0, maximum),
    }[reading]


def estimate(maximum, witnesses):
    """Original single-ticket estimate, kept byte-compatible with the baseline."""
    evidence = [(ticket, *bounds(maximum, rank, reading))
                for ticket, reading, rank in witnesses if reading != 'unreadable']
    low = max((lo for _, lo, _ in evidence), default=0)
    high = min((hi for _, _, hi in evidence), default=maximum)
    return low, high, {
        'minimum': [ticket for ticket, lo, _ in evidence if lo == low and low > 0],
        'maximum': [ticket for ticket, _, hi in evidence if hi == high and high < maximum],
        'unreadable': [ticket for ticket, reading, _ in witnesses if reading == 'unreadable'],
    }


def classify(low, high, band):
    if low > high:
        return 'contradictory'
    start, end = band
    if high < start:
        return 'below'
    if low > end:
        return 'above'
    if start <= low and high <= end:
        return 'inside'
    return 'undetermined'


def _constraints(maximum, witnesses):
    """Readable witnesses only; an unreadable ticket cannot constrain or spend budget."""
    return [(ticket, *bounds(maximum, rank, reading))
            for ticket, reading, rank in witnesses if reading in READABLE]


def _violations(constraints, value):
    return sorted(ticket for ticket, low, high in constraints
                  if not low <= value <= high)


def feasible_values(maximum, budget, witnesses):
    """Every rank that survives discarding at most `budget` readable tickets."""
    constraints = _constraints(maximum, witnesses)
    return [value for value in range(maximum + 1)
            if len(_violations(constraints, value)) <= budget]


def _segments(values):
    closed = []
    if not values:
        return closed
    start = end = values[0]
    for value in values[1:]:
        if value == end + 1:
            end = value
        else:
            closed.append([start, end])
            start = end = value
    closed.append([start, end])
    return closed


def _endpoint(constraints, value, direction, maximum):
    """Evidence at one end of a feasible closed segment.

    ``support``  readable tickets whose bound equals this endpoint, exactly the
                 tickets the original single-ticket rule would name;
    ``conflicts`` readable tickets violated at this endpoint, i.e. the ones the
                 discard budget pays for to keep it (never more than the budget);
    ``blocking`` readable tickets violated one rank outside the segment, which
                 is why the segment cannot be extended that way;
    ``outside``  that neighbouring rank, or null at the simulated boundary.
    """
    outside = value - 1 if direction == 'minimum' else value + 1
    at_edge = outside < 0 or outside > maximum
    if direction == 'minimum':
        support = sorted(ticket for ticket, low, _ in constraints
                         if value > 0 and low == value)
    else:
        support = sorted(ticket for ticket, _, high in constraints
                         if value < maximum and high == value)
    return {
        'value': value,
        'support': support,
        'conflicts': _violations(constraints, value),
        'outside': None if at_edge else outside,
        'blocking': [] if at_edge else _violations(constraints, outside),
    }


def segment_status(low, high, band):
    return classify(low, high, band)


def set_status(segments, band):
    """Classify the whole feasible set, not one segment at a time.

    ``straddling`` is separate on purpose: feasible values sit on both sides of
    the target band while no feasible value falls inside it.
    """
    if not segments:
        return 'contradictory'
    start, end = band
    below = [high < start for _, high in segments]
    above = [low > end for low, _ in segments]
    inside = [start <= low and high <= end for low, high in segments]
    touching = [not (high < start or low > end) for low, high in segments]
    if all(inside):
        return 'inside'
    if all(below):
        return 'below'
    if all(above):
        return 'above'
    if not any(touching) and any(below) and any(above):
        return 'straddling'
    return 'undetermined'


def archive_estimate(maximum, band, budget, witnesses):
    """Multi-ticket archive estimate for one rack."""
    constraints = _constraints(maximum, witnesses)
    values = feasible_values(maximum, budget, witnesses)
    closed = _segments(values)
    segments = []
    for low, high in closed:
        segments.append({
            'interval': [low, high],
            'status': segment_status(low, high, band),
            'evidence': {
                'minimum': _endpoint(constraints, low, 'minimum', maximum),
                'maximum': _endpoint(constraints, high, 'maximum', maximum),
            },
        })
    return {
        'status': set_status(closed, band),
        'segments': segments,
        'unreadable': sorted(ticket for ticket, reading, _ in witnesses
                             if reading == 'unreadable'),
    }
