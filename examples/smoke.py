import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
doc = json.loads((HERE / 'demo.json').read_text(encoding='utf-8'))
archive = json.loads((HERE / 'archive.json').read_text(encoding='utf-8'))


def invoke(payload, expected_error=None):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'source.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        cmd = [sys.executable, '-B', '-m', 'coneread', str(path)]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
    if expected_error:
        assert result.returncode == 2 and not result.stdout and expected_error in result.stderr, result
    else:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)


# --- original rack-only report ------------------------------------------------
out = invoke(doc)
racks = {r['rack']: r for r in out['racks']}
assert racks['upper']['interval'] == [4, 5] and racks['upper']['status'] == 'inside'
assert racks['door']['interval'] is None and racks['door']['status'] == 'contradictory'
assert racks['side']['evidence']['unreadable'] == ['side-b']

# --- bundle/rack archive ------------------------------------------------------
full = invoke(archive)
assert full['status'] == 'full'
pairs = {(p['bundle'], p['rack']): p for p in full['pairings']}
assert set(pairs) == {('p', 'r1'), ('p', 'r2'), ('q', 'r1'), ('q', 'r2'), ('s', 'r3')}
# The same bundle reaches different ordinals on different racks; a handoff
# narrows only the pairing it names.
assert pairs[('p', 'r1')]['interval'] == [4, 5] and pairs[('p', 'r1')]['handoff_tickets'] == ['p1']
assert pairs[('p', 'r2')]['interval'] == [2, 9] and pairs[('p', 'r2')]['handoff_tickets'] == []
assert full['in_band_count'] == {'minimum': 1, 'maximum': 3}

# Every rack's "inside/outside" claim is backed by a complete assignment.
for outlook in full['rack_outlook']:
    assert outlook['can_be_inside'] == bool(outlook['inside_bundles'])
    assert outlook['can_be_outside'] == bool(outlook['outside_bundles'])
for key in ('minimum_assignment', 'maximum_assignment'):
    assignment = full[key]
    assert len({p['rack'] for p in assignment['placements']}) == len(archive['racks'])
    assert assignment['in_band'] == sum(1 for p in assignment['placements'] if p['in_band'])
    for placement in assignment['placements']:
        low, high = placement['interval']
        assert low <= placement['ordinal'] <= high
        band = next(r['band'] for r in archive['racks'] if r['id'] == placement['rack'])
        assert placement['in_band'] == (band[0] <= placement['ordinal'] <= band[1])

# Every rack can be inside its band in *some* complete assignment, yet no single
# assignment puts all three inside: the honest answer is max=2, not 3.  The
# per-rack "inside" report must not be read as "all can be inside at once".
tension = {
    'rank_ceiling': 9, 'cone_ranks': {'q1': 1},
    'racks': [{'id': r, 'band': [0, 0]} for r in ('r1', 'r2', 'r3')],
    'bundles': [
        {'id': b, 'candidates': ['r1', 'r2', 'r3'], 'witnesses': [
            {'ticket': f'{b}0', 'cone': 'q1', 'reading': 'unreadable'}]}
        for b in ('A', 'B', 'C')],
    'handoffs': [
        {'ticket': 'A0', 'bundle': 'A', 'rack': 'r1', 'low': 0, 'high': 0},
        {'ticket': 'A0', 'bundle': 'A', 'rack': 'r2', 'low': 5, 'high': 9},
        {'ticket': 'A0', 'bundle': 'A', 'rack': 'r3', 'low': 5, 'high': 9},
        {'ticket': 'B0', 'bundle': 'B', 'rack': 'r1', 'low': 0, 'high': 0},
        {'ticket': 'B0', 'bundle': 'B', 'rack': 'r2', 'low': 5, 'high': 9},
        {'ticket': 'B0', 'bundle': 'B', 'rack': 'r3', 'low': 5, 'high': 9},
        {'ticket': 'C0', 'bundle': 'C', 'rack': 'r1', 'low': 5, 'high': 9},
        {'ticket': 'C0', 'bundle': 'C', 'rack': 'r2', 'low': 0, 'high': 0},
        {'ticket': 'C0', 'bundle': 'C', 'rack': 'r3', 'low': 0, 'high': 0},
    ],
}
tensioned = invoke(tension)
assert tensioned['in_band_count'] == {'minimum': 0, 'maximum': 2}
assert all(item['can_be_inside'] for item in tensioned['rack_outlook'])

# --- honest failure diagnostics ----------------------------------------------
contended = json.loads(json.dumps(archive))
contended['bundles'][2]['candidates'] = ['r1', 'r2']       # s can no longer use r3
impossible = invoke(contended)
assert impossible['status'] == 'impossible' and impossible['causes'] == ['rack_contention']
assert impossible['rack_contention']['demand'] > impossible['rack_contention']['supply']

emptied = json.loads(json.dumps(archive))
emptied['handoffs'][0].update(low=0, high=1)                 # p/r1 emptied by its handoff
emptied['bundles'][0]['candidates'] = ['r1']                # ...and r1 was its only rack
report = invoke(emptied)
assert report['status'] == 'impossible'
assert [e['bundle'] for e in report['handoff_emptied_pairing']] == ['p']
assert report['stranded_bundles'] == ['p']
assert report['handoff_emptied_pairing'][0]['witness_interval'] == [2, 9]
assert report['handoff_emptied_pairing'][0]['handoffs'][0]['high'] == 1

selfconflict = json.loads(json.dumps(archive))
selfconflict['bundles'][0]['witnesses'] = [
    {'ticket': 'p1', 'cone': 'q2', 'reading': 'upright'},
    {'ticket': 'p2', 'cone': 'q8', 'reading': 'fallen'}]
report = invoke(selfconflict)
assert report['status'] == 'impossible' and report['causes'] == ['bundle_self_contradiction']
assert report['bundle_self_contradiction'][0]['conflict']['lower_bound'] > \
    report['bundle_self_contradiction'][0]['conflict']['upper_bound']

# --- input rejection ----------------------------------------------------------
bad = json.loads(json.dumps(doc))
bad['racks'][0]['witnesses'][1]['cone'] = 'q4'
invoke(bad, 'invalid or repeated witness')

bad_handoff = json.loads(json.dumps(archive))
bad_handoff['handoffs'][0]['low'] = 9
bad_handoff['handoffs'][0]['high'] = 3
invoke(bad_handoff, 'ascending')

print('production smoke: PASS (coneread)')
