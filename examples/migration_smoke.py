import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from coneread.migration import EXPLICIT, FALLBACK, MISSING, MigrationState
from coneread.migration.corrections import apply_correction
from coneread.pipeline import run
old_doc = json.loads((HERE / 'migration_old.json').read_text(encoding='utf-8'))
spec = json.loads((HERE / 'migration_spec.json').read_text(encoding='utf-8'))


def invoke(*payloads, expected_error=None):
    with tempfile.TemporaryDirectory() as temp:
        paths = []
        for index, payload in enumerate(payloads):
            path = Path(temp) / f'doc{index}.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            paths.append(str(path))
        cmd = [sys.executable, '-B', '-m', 'coneread.migration', *paths]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
    if expected_error:
        assert result.returncode == 2 and not result.stdout and expected_error in result.stderr, result
        return None
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def by_rack(report):
    return {entry['rack']: entry for entry in report['racks']}


# The historical input contract and report stay untouched.
legacy = run(old_doc)
assert legacy['target_band'] == [4, 6] and len(legacy['racks']) == 4
state = MigrationState(old_doc, spec)
legacy_racks = {entry['rack']: entry for entry in legacy['racks']}
for rack, old_report in state.old_reports.items():
    assert old_report['rack_interval'] == legacy_racks[rack]['interval']
    assert old_report['band_verdict'] == legacy_racks[rack]['status']

# --- Formal migration via the real command-line entry -----------------------
formal = invoke(old_doc, spec)
assert formal['report_kind'] == 'formal_migration'
resolution = {row['old_cone']: row for row in formal['mapping_resolution']}
assert resolution['q4']['resolution'] == EXPLICIT and resolution['q4']['new_cone'] == 'n4'
assert resolution['q5']['resolution'] == EXPLICIT and resolution['q5']['new_cone'] == 'n4'
assert resolution['q6']['resolution'] == FALLBACK and resolution['q6']['new_cone'] == 'q6'
assert resolution['q7']['resolution'] == MISSING and resolution['q7']['new_cone'] is None
assert formal['missing_tickets'] == ['x-t1']

racks = by_rack(formal)
merge = racks['merge-rack']
# Two old codes merge onto one new code: original ticket IDs and constraints
# are both retained, and the contradiction stays visible.
assert merge['old_side']['band_verdict'] == 'contradictory'
assert merge['new_side']['band_verdict'] == 'contradictory'
merged = {t['ticket']: t for t in merge['diff']['tickets']}
assert merged['m-t1']['new_cone'] == 'n4' and merged['m-t2']['new_cone'] == 'n4'
assert merged['m-t1']['ticket'] == 'm-t1' and merged['m-t2']['ticket'] == 'm-t2'
assert merged['m-t2']['constraint_changed'] is True

# A missing code never becomes an unreadable ticket: the new side still reports,
# marked incomplete, with the missing ticket surfaced explicitly.
missing = racks['missing-rack']
assert missing['new_side']['complete'] is False
assert missing['new_side']['missing_tickets'] == ['x-t1']
assert missing['new_side']['ticket_constraints']['x-t1'] is None
assert missing['old_side']['band_verdict'] == 'contradictory'
assert missing['new_side']['band_verdict'] == 'below'
assert all(t != 'x-t1' for t in missing['new_side']['evidence']['unreadable'])

# Constraint changes are visible even when endpoints and verdict do not move.
fallback = racks['fallback-rack']
assert fallback['diff']['endpoint_changed'] is False
assert fallback['diff']['verdict_changed'] is False

# --- Mapping correction: explicit correction overrides same-name fallback ---
map_correction = json.loads(
    (HERE / 'correction_mapping.json').read_text(encoding='utf-8'))
map_report = invoke(old_doc, spec, map_correction)
assert map_report['full_replay_consistent'] is True
assert map_report['affected_old_cones'] == ['q6']
assert map_report['affected_tickets'] == {'fallback-rack': ['f-t1']}
assert map_report['rescanned_racks'] == ['fallback-rack']
assert 'middle-rack' in map_report['racks_not_rescanned']
path = map_report['resolution_paths'][0]
assert path['before_resolution'] == FALLBACK and path['after_resolution'] == EXPLICIT
assert path['before_new_cone'] == 'q6' and path['after_new_cone'] == 'n5'
only = map_report['rack_diffs'][0]
assert only['endpoint_changed'] is True and only['verdict_changed'] is False
assert only['before']['interval'] == [6, 7] and only['after']['interval'] == [5, 7]
# The diff against the formal migration report is carried per rack and ticket.
assert only['tickets'][0]['before']['constraint'] == [6, 9]
assert only['tickets'][0]['after']['constraint'] == [5, 9]

# --- Rank correction: endpoints and verdict unchanged, inner constraints move
rank_correction = json.loads(
    (HERE / 'correction_rank.json').read_text(encoding='utf-8'))
rank_report = invoke(old_doc, spec, rank_correction)
assert rank_report['full_replay_consistent'] is True
assert rank_report['affected_old_cones'] == ['q3']
assert rank_report['rescanned_racks'] == ['merge-rack', 'middle-rack']
assert rank_report['racks_not_rescanned'] == ['fallback-rack', 'missing-rack']
for diff in rank_report['rack_diffs']:
    assert diff['endpoint_changed'] is False
    assert diff['verdict_changed'] is False
    assert all(row['constraint_changed'] for row in diff['tickets'])

# --- In-process edge: removing an explicit mapping exposes name fallback ----
edge_doc = {
    'rank_ceiling': 9, 'band': [4, 6],
    'cone_ranks': {'q4': 4, 'q5': 5},
    'racks': [{'id': 'r1', 'witnesses': [
        {'ticket': 't-a', 'cone': 'q4', 'reading': 'fallen'},
        {'ticket': 't-b', 'cone': 'q5', 'reading': 'upright'}]}],
}
edge_spec = {
    'new_cone_ranks': {'n4': 4, 'q4': 4, 'q5': 5},
    'explicit_mapping': {'q4': 'n4'},
}
edge_state = MigrationState(edge_doc, edge_spec)
assert edge_state.resolution['q4'] == (EXPLICIT, 'n4')
assert edge_state.resolution['q5'] == (FALLBACK, 'q5')
removed = apply_correction(edge_state,
                           {'kind': 'mapping', 'old_cone': 'q4', 'new_cone': None},
                           edge_doc)
assert removed['full_replay_consistent'] is True
edge_path = removed['resolution_paths'][0]
assert edge_path['before_resolution'] == EXPLICIT
assert edge_path['after_resolution'] == FALLBACK
assert edge_path['after_new_cone'] == 'q4'

# --- In-process edge: rank correction reaches every old code merged onto it --
merge_spec = {
    'new_cone_ranks': {'n4': 4, 'q5': 5},
    'explicit_mapping': {'q4': 'n4', 'q5': 'n4'},
}
merge_state = MigrationState(edge_doc, merge_spec)
merged_rank = apply_correction(
    merge_state, {'kind': 'rank', 'new_cone': 'n4', 'new_rank': 3}, edge_doc)
assert merged_rank['full_replay_consistent'] is True
assert merged_rank['affected_old_cones'] == ['q4', 'q5']
assert merged_rank['affected_tickets'] == {'r1': ['t-a', 't-b']}
assert merged_rank['rescanned_racks'] == ['r1']

# --- In-process edge: an explicit correction explains a missing old code ----
missing_doc = {
    'rank_ceiling': 9, 'band': [4, 6],
    'cone_ranks': {'a': 4, 'b': 5},
    'racks': [{'id': 'r1', 'witnesses': [
        {'ticket': 't1', 'cone': 'a', 'reading': 'fallen'},
        {'ticket': 't2', 'cone': 'b', 'reading': 'upright'}]}],
}
missing_spec = {'new_cone_ranks': {'n4': 4}, 'explicit_mapping': {'a': 'n4'}}
missing_state = MigrationState(missing_doc, missing_spec)
assert missing_state.resolution['b'] == (MISSING, None)
explained = apply_correction(
    missing_state, {'kind': 'mapping', 'old_cone': 'b', 'new_cone': 'n4'}, missing_doc)
assert explained['full_replay_consistent'] is True
assert explained['affected_old_cones'] == ['b']
assert explained['formal_vs_corrected']['missing_tickets_before'] == ['t2']
assert explained['formal_vs_corrected']['missing_tickets_after'] == []
explained_diff = explained['rack_diffs'][0]
assert explained_diff['missing_tickets_before'] == ['t2']
assert explained_diff['missing_tickets_after'] == []

# --- Input rejection keeps exit code 2 and no partial stdout -----------------
bad_spec = dict(spec)
bad_spec['explicit_mapping'] = {'q4': 'nope'}
invoke(old_doc, bad_spec, expected_error='explicit_mapping targets unknown new cone')
invoke(old_doc, spec, {'kind': 'rank', 'new_cone': 'n3', 'new_rank': 9999},
       expected_error='corrected rank must be in 1..new_rank_ceiling')
invoke(old_doc, spec, {'kind': 'mapping', 'old_cone': 'q9', 'new_cone': 'n4'},
       expected_error='correction references unknown old cone')

print('migration smoke: PASS (coneread.migration)')
