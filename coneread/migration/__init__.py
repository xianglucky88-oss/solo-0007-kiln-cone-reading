"""Cone catalog migration: explicit mapping, name fallback, and code merges.

The historical input contract is never modified. A separate migration spec
describes the new catalog and the explicit old-code -> new-code mapping.
"""

from ..intake import parse_named, text
from ..ordinal import bounds, classify, estimate

EXPLICIT = 'explicit'
FALLBACK = 'name_fallback'
MISSING = 'unexplained_new_side'


def _ranks(spec, field, ceiling):
    ranks = spec.get(field, {})
    if not ranks or any(not text(name, 'cone') or type(rank) is not int
                        or not 1 <= rank <= ceiling
                        for name, rank in ranks.items()):
        raise ValueError(f'{field} must map cone names to ranks in 1..rank_ceiling')
    return dict(ranks)


def _mappings(spec, old_ranks, new_ranks):
    explicit = spec.get('explicit_mapping', {})
    if any(not text(old, 'old cone') or not text(new, 'new cone')
           for old, new in explicit.items()):
        raise ValueError('explicit_mapping entries must be nonempty text pairs')
    unknown = sorted(set(explicit) - set(old_ranks))
    if unknown:
        raise ValueError(f'explicit_mapping references unknown old cone: {unknown[0]}')
    unresolved = sorted(set(explicit.values()) - set(new_ranks))
    if unresolved:
        raise ValueError(f'explicit_mapping targets unknown new cone: {unresolved[0]}')
    return dict(explicit)


def build_resolution(old_ranks, new_ranks, explicit):
    """Resolve every old code: explicit wins, then same-name fallback, else missing."""
    resolution = {}
    for old in sorted(old_ranks):
        if old in explicit:
            resolution[old] = (EXPLICIT, explicit[old])
        elif old in new_ranks:
            resolution[old] = (FALLBACK, old)
        else:
            resolution[old] = (MISSING, None)
    return resolution


class MigrationState:
    """Formal migration state for one (old document, migration spec) pair."""

    def __init__(self, old_document, spec):
        self.maximum, self.band, self.old_ranks, self.old_racks = parse_named(old_document)
        new_ceiling = spec.get('new_rank_ceiling', self.maximum)
        if type(new_ceiling) is not int or not 2 <= new_ceiling <= 999:
            raise ValueError('new_rank_ceiling must be 2 through 999')
        self.new_maximum = new_ceiling
        new_band = spec.get('new_band', self.band)
        if (len(new_band) != 2 or any(type(v) is not int for v in new_band)
                or not 0 <= new_band[0] <= new_band[1] <= new_ceiling):
            raise ValueError('invalid new target band')
        self.new_band = list(new_band)
        self.new_ranks = _ranks(spec, 'new_cone_ranks', new_ceiling)
        self.explicit = _mappings(spec, self.old_ranks, self.new_ranks)
        self.resolution = build_resolution(self.old_ranks, self.new_ranks, self.explicit)
        self.ticket_index = self._index_tickets()
        self.old_reports = {name: self._old_report(rows)
                            for name, rows in self.old_racks.items()}
        self.new_reports = {name: self._new_report(name, rows)
                            for name, rows in self.old_racks.items()}

    # -- construction helpers -------------------------------------------------

    def _index_tickets(self):
        index = {}
        for rack, rows in self.old_racks.items():
            for ticket, cone, _reading, _rank in rows:
                index[ticket] = (rack, cone)
        return index

    def _old_report(self, rows):
        witnesses = [(ticket, reading, rank)
                     for ticket, _cone, reading, rank in rows]
        low, high, evidence = estimate(self.maximum, witnesses)
        return {
            'rack_interval': [low, high] if low <= high else None,
            'band_verdict': classify(low, high, self.band),
            'ticket_constraints': {
                ticket: list(bounds(self.maximum, rank, reading))
                for ticket, _cone, reading, rank in rows},
        }

    def _new_report(self, rack, rows):
        new_witnesses = []
        missing = []
        ticket_constraints = {}
        for ticket, old_cone, reading, _old_rank in rows:
            mode, new_cone = self.resolution[old_cone]
            if mode == MISSING:
                missing.append(ticket)
                ticket_constraints[ticket] = None
                continue
            rank = self.new_ranks[new_cone]
            new_witnesses.append((ticket, reading, rank))
            ticket_constraints[ticket] = list(bounds(self.new_maximum, rank, reading))
        low, high, evidence = estimate(self.new_maximum, new_witnesses)
        return {
            'complete': not missing,
            'missing_tickets': missing,
            'rack_interval': [low, high] if low <= high else None,
            'band_verdict': classify(low, high, self.new_band),
            'ticket_constraints': ticket_constraints,
            'evidence': evidence,
        }

    # -- output ---------------------------------------------------------------

    def _resolution_rows(self):
        rows = []
        for old_cone, (mode, new_cone) in sorted(self.resolution.items()):
            rows.append({
                'old_cone': old_cone,
                'resolution': mode,
                'new_cone': new_cone,
                'new_rank': None if new_cone is None else self.new_ranks[new_cone],
                'old_rank': self.old_ranks[old_cone],
            })
        return rows

    def _rack_diff(self, rack, old_report, new_report):
        old_tickets, new_tickets = {}, {}
        for ticket, interval in old_report['ticket_constraints'].items():
            old_tickets[ticket] = interval
        for ticket, interval in new_report['ticket_constraints'].items():
            new_tickets[ticket] = interval
        tickets = []
        for ticket in sorted(old_tickets):
            old_interval = old_tickets[ticket]
            new_interval = new_tickets[ticket]
            _rack, old_cone = self.ticket_index[ticket]
            mode, new_cone = self.resolution[old_cone]
            tickets.append({
                'ticket': ticket,
                'old_cone': old_cone,
                'new_cone': new_cone,
                'resolution': mode,
                'old_constraint': old_interval,
                'new_constraint': new_interval,
                'constraint_changed': old_interval != new_interval,
            })
        return {
            'rack': rack,
            'old_side': {
                'interval': old_report['rack_interval'],
                'band_verdict': old_report['band_verdict'],
            },
            'new_side': {
                'interval': new_report['rack_interval'],
                'band_verdict': new_report['band_verdict'],
                'complete': new_report['complete'],
            },
            'endpoint_changed': old_report['rack_interval'] != new_report['rack_interval'],
            'verdict_changed': old_report['band_verdict'] != new_report['band_verdict'],
            'tickets': tickets,
        }

    def formal_report(self):
        missing_tickets = sorted(
            ticket for ticket, (_rack, cone) in self.ticket_index.items()
            if self.resolution[cone][0] == MISSING)
        return {
            'report_kind': 'formal_migration',
            'old_side': {
                'rank_ceiling': self.maximum,
                'target_band': self.band,
                'cone_ranks': dict(sorted(self.old_ranks.items())),
            },
            'new_side': {
                'rank_ceiling': self.new_maximum,
                'target_band': self.new_band,
                'cone_ranks': dict(sorted(self.new_ranks.items())),
            },
            'mapping_resolution': self._resolution_rows(),
            'missing_tickets': missing_tickets,
            'racks': [
                {
                    'rack': rack,
                    'old_side': self.old_reports[rack],
                    'new_side': self.new_reports[rack],
                    'diff': self._rack_diff(rack, self.old_reports[rack],
                                            self.new_reports[rack]),
                }
                for rack in sorted(self.old_racks)],
        }
