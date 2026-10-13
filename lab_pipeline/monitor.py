"""Small read-only status snapshot for the server workflow."""
import json
from pathlib import Path
from datetime import datetime, timezone

root = Path('/volume/wzhang/mesh-research-workspace/micmac')
run = root / 'lab_runs/mangrove-077-full405'
snapshot = {'checked_utc': datetime.now(timezone.utc).isoformat()}
status = run / 'status.json'
if status.exists():
    state = json.loads(status.read_text())
    snapshot.update({k: state.get(k) for k in ('status', 'stage', 'pid', 'updated_utc', 'error')})
    snapshot['stages'] = {k: {'status': v.get('status'), 'elapsed_seconds': v.get('elapsed_seconds')}
                          for k, v in state['stages'].items()}
    snapshot['orientation_counts'] = {name: len(list((run / ('Ori-' + name)).glob('Orientation-*.xml')))
                                      for name in ('Arbitrary', 'Ground_RTL', 'Ground_PROJ')}
    snapshot['individual_orthos'] = len(list((run / 'Ortho-MEC-Malt').glob('Ort_*.tif')))
    stage_log = run / 'logs' / (str(state.get('stage')) + '.log')
    if stage_log.exists():
        with stage_log.open('rb') as stream:
            stream.seek(max(0, stage_log.stat().st_size - 4096))
            snapshot['log_tail'] = stream.read().decode(errors='replace').splitlines()[-10:]
    snapshot['pipeline_pid_exists'] = Path('/proc/' + str(state.get('pid'))).exists()
else:
    build_log = root / '.lab/build.log'
    if build_log.exists():
        with build_log.open('rb') as stream:
            stream.seek(max(0, build_log.stat().st_size - 4096))
            snapshot['build_tail'] = stream.read().decode(errors='replace').splitlines()[-8:]
        snapshot['build_ready'] = b'MICMAC_BUILD_READY=' in build_log.read_bytes()[-4096:]
print(json.dumps(snapshot, ensure_ascii=False, indent=2))
