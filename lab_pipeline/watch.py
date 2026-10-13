"""Stream compact progress; computation continues independently if this watcher exits."""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

root = Path('/volume/wzhang/mesh-research-workspace/micmac')
run = root / 'lab_runs/mangrove-077-full405'
while True:
    state = json.loads((run / 'status.json').read_text())
    stage = state.get('stage')
    result = {'utc': datetime.now(timezone.utc).isoformat(), 'status': state['status'], 'stage': stage}
    if stage == '04_tie_points':
        result['feature_files'] = len(list((run / 'Pastis').glob('LBPpResol*.tif.dat')))
        result['pair_result_files'] = len(list((run / 'Pastis').glob('LBPp-Match-*/*.result')))
        result['homologous_files'] = len(list((run / 'Homol').glob('Pastis*/*.dat')))
    if stage in ('01_gps_text', '02_gps_local'):
        result['gps_camera_files'] = len(list((run / 'Ori-RAWGNSS').glob('Orientation-*.xml')))
    if stage and stage.startswith(('05', '06', '07', '08')):
        result['cameras'] = {name: len(list((run / ('Ori-' + name)).glob('Orientation-*.xml')))
                             for name in ('Arbitrary', 'Ground_RTL', 'Ground_PROJ')}
    path = run / 'logs' / (stage + '.log') if stage else None
    if path and path.exists():
        if stage == '05_sfm':
            result['pose_additions'] = path.read_text(errors='replace').count('Add Pose =')
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 6000))
            tail = stream.read().decode(errors='replace')
        result['log_tail'] = [line[:250] for line in tail.splitlines()[-3:]]
    if stage == '09_dense_and_orthorectification':
        result['individual_rgb_orthos'] = len(list((run / 'Ortho-MEC-Malt').glob('Ort_*.tif')))
        phases = re.findall(r'FirstEtapeMEC=(\d+) LastEtapeMEC=(\d+)', tail)
        result['dense_phase'] = phases[-1] if phases else None
    supervisor = json.loads((root / '.lab/full_job_status.json').read_text())
    result['supervisor'] = supervisor['status']
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if supervisor['status'] in ('complete', 'failed'):
        break
    time.sleep(45)
