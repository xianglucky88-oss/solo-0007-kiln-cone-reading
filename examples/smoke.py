import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
doc = json.loads((HERE / 'demo.json').read_text(encoding='utf-8'))


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


out = invoke(doc)
racks = {r['rack']: r for r in out['racks']}
assert racks['upper']['interval'] == [4, 5] and racks['upper']['status'] == 'inside'
assert racks['door']['interval'] is None and racks['door']['status'] == 'contradictory'
assert racks['side']['evidence']['unreadable'] == ['side-b']
doc['racks'][0]['witnesses'][1]['cone'] = 'q4'
invoke(doc, 'invalid or repeated witness')
print('production smoke: PASS (coneread)')
