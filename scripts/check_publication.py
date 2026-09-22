"""Fail closed for unreviewed files and common credential patterns; never print secrets."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    '.gitignore', '.gitattributes', 'README.md', 'LICENSE', 'requirements.txt',
    'transcribe_betagaki_gui.py', 'start_gui_windows.bat', 'start_gui_mac.command',
    'AGENTS.md', 'scripts/check_publication.py', 'tests/test_transcriber.py',
    'tests/test_publication.py', 'docs/PUBLISHING.md', 'docs/VALIDATION.md',
    'docs/issues/01-initial-publication.md', 'docs/issues/02-platform-smoke-tests.md',
    'docs/issues/03-maintenance.md', '.github/workflows/ci.yml',
    '.github/ISSUE_TEMPLATE/bug_report.md', '.github/ISSUE_TEMPLATE/codex_task.md',
    '.github/pull_request_template.md', 'docs/images/app-macos.png',
}
SECRET = re.compile(rb'(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def audit(root=ROOT):
    failures = []
    # All files on disk, including ignored files, except tooling caches and git internals.
    ignored_dirs = {'.git', '.venv', '__pycache__', '.pytest_cache'}
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if any(part in ignored_dirs for part in relative.parts):
            continue
        if path.is_symlink():
            failures.append('symlink is not allowed')
        elif path.is_file():
            if relative.as_posix() not in ALLOWED:
                failures.append('unapproved file is present')
            elif SECRET.search(path.read_bytes()):
                failures.append('possible secret in approved file')
    # Audit index AND history when this directory is itself a Git repository.
    # A parent project's Git history must never be included accidentally.
    top = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True)
    if top.returncode == 0 and Path(top.stdout.decode().strip()).resolve() == root.resolve():
        tracked = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).split(b'\0')
        for name in filter(None, tracked):
            if name.decode('utf-8') not in ALLOWED:
                failures.append('unapproved tracked file')
            data = subprocess.check_output(['git', '-C', str(root), 'show', ':' + name.decode('utf-8')])
            if SECRET.search(data):
                failures.append('possible secret in index')
        rev = subprocess.run(['git', '-C', str(root), 'rev-list', '--all'], capture_output=True, check=True)
        for commit in rev.stdout.decode().splitlines():
            listing = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '-z', commit])
            for item in filter(None, listing.split(b'\0')):
                metadata, name = item.split(b'\t', 1)
                mode, kind, oid = metadata.split()
                if name.decode('utf-8') not in ALLOWED or mode not in (b'100644', b'100755'):
                    failures.append('unapproved historical path or mode')
                if kind == b'blob':
                    data = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', oid.decode()])
                    if SECRET.search(data):
                        failures.append('possible secret in history')
    return sorted(set(failures))


if __name__ == '__main__':
    problems = audit()
    for problem in problems:
        print('FAIL:', problem)
    print('Publication check:', 'FAIL' if problems else 'PASS')
    print('Review approved documents manually too; arbitrary private prose cannot be detected reliably.')
    sys.exit(bool(problems))
