import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

root = Path('/volume/wzhang/mesh-research-workspace/micmac')
api = json.loads((root / '.lab/upstream_api.json').read_text())
revision = api['sha']
archive = root / '.lab' / (revision + '.tar.gz')
url = 'https://codeload.github.com/micmacIGN/micmac/tar.gz/' + revision
subprocess.run(['curl', '-x', 'http://127.0.0.1:17995', '--fail', '--location',
                '--retry', '3', '--connect-timeout', '30', '--max-time', '1800',
                url, '-o', str(archive)], check=True)
print('SOURCE_ARCHIVE_DOWNLOADED', archive.stat().st_size, flush=True)
with tarfile.open(archive) as stream:
    members = stream.getmembers()
    prefix = members[0].name.split('/')[0] + '/'
    for member in members:
        if member.name == prefix[:-1]:
            continue
        if not member.name.startswith(prefix):
            raise RuntimeError('Unexpected archive prefix')
        relative = Path(member.name[len(prefix):])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] in ('.git', '.lab', 'lab_pipeline'):
            raise RuntimeError('Archive path outside source checkout')
        member.name = str(relative)
        stream.extract(member, root, filter='data')
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
provenance = {'repository': 'https://github.com/micmacIGN/micmac', 'upstream_revision': revision,
              'upstream_commit_date': api['commit']['committer']['date'],
              'archive_url': url, 'archive_sha256': digest,
              'acquisition': 'Official commit-pinned source archive; local Git snapshot'}
(root / 'lab_pipeline/source_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
(root / '.lab/upstream_revision.txt').write_text(revision + '\n')
print('SOURCE_READY', revision, digest, flush=True)
agents = list(root.rglob('AGENTS.md'))
print('REPOSITORY_INSTRUCTIONS', [str(path) for path in agents], flush=True)
