"""Wait for this build, run all reconstruction stages, then verify the full GeoTIFF."""
import json
import os
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

root = Path('/volume/wzhang/mesh-research-workspace/micmac')
job_status = root / '.lab/full_job_status.json'
state = {'status': 'waiting_for_build', 'pid': os.getpid(), 'started_utc': datetime.now(timezone.utc).isoformat()}
def update(**values):
    state.update(values, updated_utc=datetime.now(timezone.utc).isoformat())
    temp = job_status.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2) + '\n')
    temp.replace(job_status)
try:
    update()
    build_pid = json.loads((root / '.lab/build_job.json').read_text())['pid']
    deadline = time.monotonic() + 7200
    while True:
        log = (root / '.lab/build.log').read_bytes()[-8192:]
        if b'MICMAC_BUILD_READY=' in log:
            break
        if not Path('/proc/' + str(build_pid)).exists() or time.monotonic() > deadline:
            raise RuntimeError('Build did not finish successfully; inspect .lab/build.log')
        time.sleep(10)
    update(status='reconstructing')
    subprocess.run(['/usr/bin/python3', '-u', str(root / 'lab_pipeline/run_micmac.py'),
                    '--threads', '64', '--resolution', '0.03',
                    '--ba-calibration-mode', 'fixed', '--recover-failed-ba'], check=True)
    update(status='verifying')
    subprocess.run(['/usr/bin/python3', str(root / 'lab_pipeline/verify_orthophoto.py')], check=True)
    update(status='complete')
    print('FULL_HIGH_RESOLUTION_ORTHOPHOTO_VERIFIED', flush=True)
except Exception:
    update(status='failed', error=traceback.format_exc())
    raise
