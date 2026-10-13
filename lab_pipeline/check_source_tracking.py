"""Track original archive files even when upstream .gitignore matches them."""
import json
import subprocess
import tarfile
from pathlib import Path
root = Path('/volume/wzhang/mesh-research-workspace/micmac')
revision = (root / '.lab/upstream_revision.txt').read_text().strip()
tracked = set(subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0'))
with tarfile.open(root / '.lab' / (revision + '.tar.gz')) as stream:
    names = [member.name.split('/', 1)[1] for member in stream.getmembers()
             if member.isfile() or member.issym()]
missing = sorted(set(names) - tracked)
if missing:
    subprocess.run(['git', '-C', str(root), 'add', '-f', '--pathspec-from-file=-', '--pathspec-file-nul'],
                   input='\0'.join(missing).encode() + b'\0', check=True)
    subprocess.run(['git', '-C', str(root), 'commit', '--quiet', '-m',
                    'Track all official source archive files including upstream ignored paths'], check=True)
print(json.dumps({'archive_source_files': len(names), 'added_previously_ignored': len(missing)}))
