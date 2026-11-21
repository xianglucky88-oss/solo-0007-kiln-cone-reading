"""Archivist corrections applied on top of a formal migration state.

Only racks whose tickets reference corrected codes are rescanned; every other
rack is carried over untouched. Each correction result is checked against a
full replay under the corrected catalog, without modifying the old input.
"""

from . import MigrationState, build_resolution

MAPPING = 'mapping'
RANK = 'rank'


def _correction(document):
    kind = document.get('kind')
    if kind not in (MAPPING, RANK):
        raise ValueError('correction kind must be "mapping" or "rank"')
    if kind == MAPPING:
        old_cone = document.get('old_cone')
        new_cone = document.get('new_cone')
        if not isinstance(old_cone, str) or not old_cone.strip():
            raise ValueError('mapping correction needs old_cone')
        if new_cone is not None and (not isinstance(new_cone, str) or not new_cone.strip()):
            raise ValueError('mapping correction new_cone must be text or null')
        return kind, old_cone, new_cone
    new_cone = document.get('new_cone')
    new_rank = document.get('new_rank')
    if not isinstance(new_cone, str) or not new_cone.strip():
        raise ValueError('rank correction needs new_cone')
    if type(new_rank) is not int:
        raise ValueError('rank correction needs integer new_rank')
    return kind, new_cone, new_rank


def _apply_correction(state, correction):
    kind, first, second = _correction(correction)
    explicit = dict(state.explicit)
    new_ranks = dict(state.new_ranks)
    if kind == MAPPING:
        old_cone, new_cone = first, second
        if old_cone not in state.old_ranks:
            raise ValueError(f'correction references unknown old cone: {old_cone}')
        if new_cone is None:
            explicit.pop(old_cone, None)
        else:
            if new_cone not in new_ranks:
                raise ValueError(f'correction targets unknown new cone: {new_cone}')
            explicit[old_cone] = new_cone
    else:
        new_cone, new_rank = first, second
        if new_cone not in new_ranks:
            raise ValueError(f'correction references unknown new cone: {new_cone}')
        if not 1 <= new_rank <= state.new_maximum:
            raise ValueError('corrected rank must be in 1..new_rank_ceiling')
        new_ranks[new_cone] = new_rank
    return kind, first, second, explicit, new_ranks


def _affected_cones(state, kind, first, corrected_explicit, corrected_new_ranks):
    """Old cones whose direct or fallback resolution moves due to the correction."""
    before = state.resolution
    after = build_resolution(state.old_ranks, corrected_new_ranks, corrected_explicit)
    affected = set()
    if kind == MAPPING:
        old_cone = first
        for cone, (mode, target) in after.items():
            before_mode, before_target = before[cone]
            if (mode, target) != (before_mode, before_target):
                affected.add(cone)
        # Directly corrected old cone is always listed, even if its resolved
        # target happens to remain the same cone via a different path.
        affected.add(old_cone)
    else:
        new_cone = first
        for cone, (mode, target) in after.items():
            if target == new_cone or before[cone][1] == new_cone:
                affected.add(cone)
    return affected, before, after


def _rack_summary(rack, report):
    return {
        'rack': rack,
        'interval': report['rack_interval'],
        'band_verdict': report['band_verdict'],
        'complete': report['complete'],
    }


def _correction_rack_diff(formal_state, corrected_state, affected_tickets):
    diffs = []
    for rack in sorted(affected_tickets):
        before = formal_state.new_reports[rack]
        after = corrected_state.new_reports[rack]
        old_report = formal_state.old_reports[rack]
        ticket_rows = []
        for ticket in sorted(affected_tickets[rack]):
            _rack_owner, old_cone = formal_state.ticket_index[ticket]
            ticket_rows.append({
                'ticket': ticket,
                'old_cone': old_cone,
                'before': {
                    'resolution': formal_state.resolution[old_cone][0],
                    'new_cone': formal_state.resolution[old_cone][1],
                    'constraint': before['ticket_constraints'][ticket],
                },
                'after': {
                    'resolution': corrected_state.resolution[old_cone][0],
                    'new_cone': corrected_state.resolution[old_cone][1],
                    'constraint': after['ticket_constraints'][ticket],
                },
                'constraint_changed':
                    before['ticket_constraints'][ticket]
                    != after['ticket_constraints'][ticket],
            })
        diffs.append({
            'rack': rack,
            'before': _rack_summary(rack, before),
            'after': _rack_summary(rack, after),
            'endpoint_changed': before['rack_interval'] != after['rack_interval'],
            'verdict_changed': before['band_verdict'] != after['band_verdict'],
            'missing_tickets_before': list(before['missing_tickets']),
            'missing_tickets_after': list(after['missing_tickets']),
            'old_side_reference': {
                'interval': old_report['rack_interval'],
                'band_verdict': old_report['band_verdict'],
            },
            'tickets': ticket_rows,
        })
    return diffs


def _replay_spec(state, corrected_explicit, corrected_new_ranks):
    return {
        'new_rank_ceiling': state.new_maximum,
        'new_band': state.new_band,
        'new_cone_ranks': corrected_new_ranks,
        'explicit_mapping': corrected_explicit,
    }


def apply_correction(state, correction, old_document):
    """Incremental correction report, verified against a full catalog replay."""
    kind, first, second, corrected_explicit, corrected_new_ranks = _apply_correction(
        state, correction)
    affected_cones, before_resolution, after_resolution = _affected_cones(
        state, kind, first, corrected_explicit, corrected_new_ranks)

    affected_tickets = {}
    for ticket, (rack, cone) in state.ticket_index.items():
        if cone in affected_cones:
            affected_tickets.setdefault(rack, set()).add(ticket)
    scanned_racks = sorted(affected_tickets)
    skipped_racks = sorted(set(state.old_racks) - set(scanned_racks))

    # Incremental result: rescanned racks come from the corrected replay,
    # every other rack is carried over verbatim from the formal report.
    corrected_state = MigrationState(old_document,
                                     _replay_spec(state, corrected_explicit, corrected_new_ranks))

    rack_diffs = _correction_rack_diff(state, corrected_state, affected_tickets)
    incremental_new = {}
    for rack in state.old_racks:
        if rack in affected_tickets:
            incremental_new[rack] = corrected_state.new_reports[rack]
        else:
            incremental_new[rack] = state.new_reports[rack]

    # Full-replay consistency: replaying the whole corrected catalog must
    # produce exactly the incremental result, proving skipped racks needed
    # no rescan and the rescanned racks match the full replay.
    replay_new = {rack: corrected_state.new_reports[rack] for rack in state.old_racks}
    replay_mismatches = [
        {'rack': rack, 'where': 'rescanned_rack' if rack in affected_tickets else 'carried_rack'}
        for rack in state.old_racks if incremental_new[rack] != replay_new[rack]
    ]

    changed_paths = []
    for cone in sorted(affected_cones):
        b_mode, b_target = before_resolution[cone]
        a_mode, a_target = after_resolution[cone]
        changed_paths.append({
            'old_cone': cone,
            'direct': kind == MAPPING and cone == first,
            'via_fallback': not (kind == MAPPING and cone == first),
            'before_resolution': b_mode,
            'before_new_cone': b_target,
            'after_resolution': a_mode,
            'after_new_cone': a_target,
        })

    if kind == MAPPING:
        correction_entry = {'kind': MAPPING, 'old_cone': first, 'new_cone': second}
    else:
        correction_entry = {'kind': RANK, 'new_cone': first,
                            'old_rank': state.new_ranks[first], 'new_rank': second}

    return {
        'report_kind': 'correction_replay',
        'correction': correction_entry,
        'affected_old_cones': sorted(affected_cones),
        'resolution_paths': changed_paths,
        'affected_tickets': {rack: sorted(tickets)
                             for rack, tickets in sorted(affected_tickets.items())},
        'rescanned_racks': scanned_racks,
        'racks_not_rescanned': skipped_racks,
        'rack_diffs': rack_diffs,
        'formal_vs_corrected': {
            'missing_tickets_before': state.formal_report()['missing_tickets'],
            'missing_tickets_after': corrected_state.formal_report()['missing_tickets'],
        },
        'full_replay_consistent': not replay_mismatches,
        'replay_mismatches': replay_mismatches,
    }
