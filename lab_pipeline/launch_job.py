"""Launch one task-owned job with persistent logs, independently of SSH."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('name')
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()
root = Path('/volume/wzhang/mesh-research-workspace/micmac')
if not args.command or args.name not in ('build', 'pipeline', 'verification'):
    raise ValueError('Expected named MicMac build, pipeline or verification command')
with (root / '.lab' / (args.name + '.log')).open('a') as log:
    process = subprocess.Popen(args.command, cwd=root, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
record = {'pid': process.pid, 'started_utc': datetime.now(timezone.utc).isoformat(),
          'command': args.command}
(root / '.lab' / (args.name + '_job.json')).write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
