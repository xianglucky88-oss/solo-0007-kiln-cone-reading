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


# --- legacy single-ticket mode stays as it was ---
out = invoke(doc)
racks = {r['rack']: r for r in out['racks']}
assert racks['upper']['interval'] == [4, 5] and racks['upper']['status'] == 'inside'
assert racks['door']['interval'] is None and racks['door']['status'] == 'contradictory'
assert racks['side']['evidence']['unreadable'] == ['side-b']
doc['racks'][0]['witnesses'][1]['cone'] = 'q4'
invoke(doc, 'invalid or repeated witness')

# --- new archive mode ---
doc = json.loads((HERE / 'demo.json').read_text(encoding='utf-8'))
out = invoke(archive)
racks = {r['rack']: r for r in out['racks']}

upper = racks['upper']
assert [s['interval'] for s in upper['segments']] == [[0, 3]]
assert upper['status'] == 'below' and upper['unreadable'] == ['up-note']
top = upper['segments'][0]['evidence']['maximum']
assert top['value'] == 3 and top['support'] == ['up-u4', 'up-u4-dup']
assert top['conflicts'] == ['up-f5'] and top['blocking'] and top['outside'] == 4
# every endpoint names concrete conflicting tickets, so each closed segment is accounted for
for rack in out['racks']:
    for segment in rack['segments']:
        for end in ('minimum', 'maximum'):
            evidence = segment['evidence'][end]
            assert len(evidence['conflicts']) <= rack['budget'], (rack['rack'], evidence)
            if evidence['outside'] is not None:
                assert len(evidence['blocking']) > rack['budget'], (rack['rack'], evidence)

split = racks['split']
assert [s['interval'] for s in split['segments']] == [[0, 3], [7, 9]]
assert split['status'] == 'straddling' and split['interval'] is None
assert split['segments'][0]['status'] == 'below' and split['segments'][1]['status'] == 'above'
assert split['unreadable'] == ['sp-note']

link = racks['link']
assert [s['interval'] for s in link['segments']] == [[0, 0], [2, 9]]
assert link['budget'] == 2
assert link['segments'][0]['evidence']['maximum']['outside'] == 1

door = racks['door']
assert [s['interval'] for s in door['segments']] == [[0, 3], [6, 9]]
assert door['segments'][0]['evidence']['maximum']['conflicts'] == ['dr-f']

# a second readable ticket on the same cone is fine; a repeated ticket id is not
same_cone = json.loads(json.dumps(archive))
invoke(same_cone)
repeated = json.loads(json.dumps(archive))
repeated['racks'][0]['witnesses'].append({'ticket': 'up-f5', 'cone': 'q6', 'reading': 'upright'})
invoke(repeated, 'invalid or repeated witness')
bad_reading = json.loads(json.dumps(archive))
bad_reading['racks'][0]['witnesses'][0]['reading'] = 'mostly'
invoke(bad_reading, 'invalid or repeated witness')
bad_budget = json.loads(json.dumps(archive))
bad_budget['budget'] = -1
invoke(bad_budget, 'must be a nonnegative integer')

# --- archive recovery from the saved report alone, then amendment recompute ---
snapshot = out['archive']

# ln-f2 is non-extreme: the tightest lower bound comes from ln-f3 (rank 3, not
# ln-f2's rank 2) and the tightest upper bound from ln-u1.  Retracting just this
# non-extreme ticket joins the two feasible ranges.
recomputed = invoke({'archive': snapshot, 'amendments': {'retractions': ['ln-f2']}})
assert recomputed['touched'] == ['link']
assert recomputed['untouched'] == ['door', 'split', 'upper']
assert [r['rack'] for r in recomputed['racks']] == ['link']
changes = recomputed['racks'][0]['changes']
assert changes['amended']['retracted'] == ['ln-f2']
assert changes['status'] == {'from': 'undetermined', 'to': 'undetermined'}
assert [s['interval'] for s in recomputed['racks'][0]['segments']] == [[0, 9]]
assert changes['added_intervals'] == [[1, 1]] and changes['removed_intervals'] == []

# a correction that moves only the endpoint evidence, not the feasible range
same_range = invoke({'archive': snapshot,
                     'amendments': {'corrections': [{'ticket': 'ln-f2', 'reading': 'bending', 'cone': 'q3'}]}})
changes = same_range['racks'][0]['changes']
assert [s['interval'] for s in same_range['racks'][0]['segments']] == [[0, 0], [2, 9]]
assert changes['added_intervals'] == [] and changes['removed_intervals'] == []
assert changes['status']['from'] == changes['status']['to']
assert changes['evidence_changed']
assert changes['unchanged'] is False

# a correction that exactly spends the budget, removing and adding ranges
spent = invoke({'archive': snapshot,
                'amendments': {'corrections': [{'ticket': 'dr-f', 'reading': 'bending', 'cone': 'q5'}]}})
door = spent['racks'][0]
assert door['rack'] == 'door'
assert [s['interval'] for s in door['segments']] == [[0, 5]]
assert door['segments'][0]['evidence']['maximum']['conflicts'] == ['dr-u']
assert spent['untouched'] == ['link', 'split', 'upper']

# a correction touching only unreadable tickets leaves the analysis untouched,
# yet the refreshed snapshot still equals a recomputation from the source
quiet = invoke({'archive': snapshot,
                'amendments': {'corrections': [{'ticket': 'up-note', 'reading': 'unreadable', 'cone': 'q1'}]}})
assert quiet['touched'] == ['upper']
assert quiet['untouched'] == ['door', 'link', 'split']
assert [s['interval'] for s in quiet['racks'][0]['segments']] == [[0, 3]]
assert quiet['racks'][0]['changes']['unchanged'] is True
updated_source = json.loads(json.dumps(archive))
for witness in updated_source['racks'][0]['witnesses']:
    if witness['ticket'] == 'up-note':
        witness['cone'] = 'q1'
assert quiet['archive'] == invoke(updated_source)['archive']
assert invoke(quiet['archive'])['racks'] == invoke(updated_source)['racks']

# re-analyzing only touched racks: counting the analyses the pipeline performs
sys.path.insert(0, str(ROOT))
import coneread.pipeline as pipeline
calls = []
original = pipeline._analyze
pipeline._analyze = lambda state, rack: (calls.append(rack['id']), original(state, rack))[1]
try:
    pipeline.run({'archive': snapshot, 'amendments': {'retractions': ['ln-f3']}})
finally:
    pipeline._analyze = original
assert calls == ['link', 'link'], calls

# unknown tickets and conflicting amendments are rejected without partial output
invoke({'archive': snapshot, 'amendments': {'retractions': ['no-such-ticket']}}, 'unknown ticket')
invoke({'archive': snapshot,
        'amendments': {'corrections': [{'ticket': 'ln-f2', 'reading': 'fallen'}],
                       'retractions': ['ln-f2']}}, 'conflicting amendment')

# the refreshed snapshot is itself a valid archive input
again = invoke(snapshot)
assert again['archive'] == snapshot
assert [r['rack'] for r in again['racks']] == [r['rack'] for r in out['racks']]

print('production smoke: PASS (coneread)')
