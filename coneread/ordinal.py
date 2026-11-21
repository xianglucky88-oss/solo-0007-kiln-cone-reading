"""Ordinal endpoints, witness preservation and interval helpers.

Readings are translated into closed integer intervals of possible ordinals:
fallen gives a lower bound, upright an upper bound, bending restricts the cone
to two adjacent ordinals and unreadable contributes no constraint.
"""


def bounds(maximum, rank, reading):
    return {
        'fallen': (rank, maximum),
        'upright': (0, rank - 1),
        'bending': (rank - 1, rank),
        'unreadable': (0, maximum),
    }[reading]


def estimate(maximum, witnesses):
    """Return ``(low, high, evidence)`` for ``(ticket, reading, rank)`` rows."""
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


def intersect(first, second):
    """Intersect two closed integer intervals; return ``None`` when disjoint."""
    low = max(first[0], second[0])
    high = min(first[1], second[1])
    return (low, high) if low <= high else None


def band_relation(interval, band):
    """How a pairing's allowed ordinals relate to one rack's recipe band.

    ``'inside'``: every allowed ordinal is in the band.
    ``'outside'``: no allowed ordinal is in the band.
    ``'mixed'``: the band and the allowed set overlap without containment.
    """
    low, high = interval
    start, end = band
    inside = max(low, start) <= min(high, end)
    outside = low < start or high > end
    if inside and outside:
        return 'mixed'
    return 'inside' if inside else 'outside'
