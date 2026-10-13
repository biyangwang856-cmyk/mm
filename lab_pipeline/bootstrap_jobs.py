import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

root = Path('/volume/wzhang/mesh-research-workspace/micmac')
logs = root / '.lab'
source = next(p for p in (root.parent / 'datasets').iterdir()
              if p.is_dir() and len(list(p.glob('*.JPG'))) == 405)
jobs = {}
commands = {
    'copy': ['python3', str(root / 'lab_pipeline/prepare_dataset.py'),
             '--root', str(root), '--source', str(source), '--expected-count', '405', '--copy-only'],
    'dependencies': ['bash', str(root / 'lab_pipeline/install_dependencies.sh')],
}
for name, command in commands.items():
    with (logs / (name + '.log')).open('a') as stream:
        proc = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    jobs[name] = {'pid': proc.pid, 'command': command}
jobs['started_utc'] = datetime.now(timezone.utc).isoformat()
(logs / 'bootstrap_jobs.json').write_text(json.dumps(jobs, ensure_ascii=False, indent=2))
print(json.dumps(jobs, ensure_ascii=False))
