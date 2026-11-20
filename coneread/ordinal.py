def bounds(maximum, rank, reading):
    return {
        'fallen': (rank, maximum),
        'upright': (0, rank - 1),
        'bending': (rank - 1, rank),
        'unreadable': (0, maximum),
    }[reading]


def estimate(maximum, witnesses):
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
