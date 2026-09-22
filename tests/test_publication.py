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
            result = subprocess.run(['git', '-C', directory, 'check-ignore', '--stdin', '-z'],
                                    input=('\0'.join(private) + '\0').encode('utf-8'),
                                    capture_output=True, check=True)
            self.assertEqual(result.stdout.decode('utf-8').rstrip('\0').split('\0'), private)
            result = subprocess.run(['git', '-C', directory, 'check-ignore', 'requirements.txt'], capture_output=True)
            self.assertEqual(result.returncode, 1)
