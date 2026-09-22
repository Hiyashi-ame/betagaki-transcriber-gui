from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.check_publication import audit


class PublicationTests(unittest.TestCase):
    def test_private_files_and_secrets_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(audit(root), [])
            (root / 'recording.M4A').touch()
            self.assertTrue(audit(root))
            (root / 'recording.M4A').unlink()
            (root / 'README.md').write_text('sk-' + 'x' * 40)
            self.assertTrue(audit(root))

    def test_deleted_secret_in_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', directory, *args], check=True, capture_output=True)
            git('init')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            (root / 'README.md').write_text('sk-' + 'x' * 40)
            git('add', 'README.md')
            git('commit', '-m', 'synthetic fixture')
            (root / 'README.md').write_text('clean')
            git('add', 'README.md')
            git('commit', '-m', 'clean fixture')
            self.assertIn('possible secret in history', audit(root))

    def test_gitignore_excludes_runtime_data(self):
        source = Path(__file__).resolve().parents[1] / '.gitignore'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', directory], check=True, capture_output=True)
            (root / '.gitignore').write_bytes(source.read_bytes())
            private = ['sample.M4A', 'sample/sample.txt', '.env', '_chunks_123/chunk.mp3', 'secret.json']
            result = subprocess.run(['git', '-C', directory, 'check-ignore', '--stdin'],
                                    input='\n'.join(private), text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.splitlines(), private)
            result = subprocess.run(['git', '-C', directory, 'check-ignore', 'requirements.txt'], capture_output=True)
            self.assertEqual(result.returncode, 1)
