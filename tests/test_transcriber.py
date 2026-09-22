import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import transcribe_betagaki_gui as app


class TranscriberTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / '日本語 音声.m4a'
        self.source.touch()
        self.stop = threading.Event()

    def chunks(self, source, directory, seconds, stop):
        paths = [directory / f'{index}.mp3' for index in range(2)]
        for path in paths:
            path.write_bytes(b'synthetic')
        return paths

    def client(self, callback):
        return SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=callback)))

    def test_batch_case_insensitive_nonrecursive(self):
        (self.folder / 'SECOND.M4A').touch()
        (self.folder / 'ignored.mp3').touch()
        child = self.folder / 'nested'
        child.mkdir()
        (child / 'ignored.m4a').touch()
        self.assertEqual(len(app.collect_inputs(self.folder, True)), 2)
        self.assertEqual(app.collect_inputs(self.source, False), [self.source])

    def test_success_output_and_cleanup(self):
        calls = []
        def call(**kwargs):
            calls.append(kwargs)
            self.assertEqual(kwargs['response_format'], 'json')
            self.assertFalse(kwargs['file'].closed)
            return SimpleNamespace(text='synthetic test response')
        with patch.object(app, 'split_audio', self.chunks):
            output = app.transcribe_file(self.source, self.client(call), app.MODELS[0], 120, self.stop, lambda _: None)
        self.assertEqual(output.name, self.source.stem + '.txt')
        self.assertEqual(len(output.read_text().splitlines()), 2)
        self.assertEqual(list(output.parent.iterdir()), [output])
        self.assertTrue(all(c['file'].closed for c in calls))

    def test_existing_output_is_preserved(self):
        output = self.source.with_suffix('')
        output.mkdir()
        marker = output / 'keep.txt'
        marker.write_text('preserve')
        with self.assertRaises(app.UserError):
            app.transcribe_file(self.source, None, app.MODELS[0], 120, self.stop, lambda _: None)
        self.assertEqual(marker.read_text(), 'preserve')

    def test_failure_keeps_partial_and_removes_chunks(self):
        count = 0
        def call(**kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('private response must not be shown')
            return SimpleNamespace(text='synthetic test response')
        with patch.object(app, 'split_audio', self.chunks), self.assertRaises(RuntimeError):
            app.transcribe_file(self.source, self.client(call), app.MODELS[0], 120, self.stop, lambda _: None)
        files = list(self.source.with_suffix('').iterdir())
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].name.endswith('.partial.txt'))
        self.assertEqual(len(files[0].read_text().splitlines()), 1)

    def test_cancel_after_response_keeps_partial(self):
        def call(**kwargs):
            self.stop.set()
            return SimpleNamespace(text='synthetic test response')
        with patch.object(app, 'split_audio', self.chunks), self.assertRaises(app.Cancelled):
            app.transcribe_file(self.source, self.client(call), app.MODELS[0], 120, self.stop, lambda _: None)
        self.assertEqual(len(list(self.source.with_suffix('').iterdir())), 1)
        self.assertFalse((self.source.with_suffix('') / (self.source.stem + '.txt')).exists())

    def test_cancel_before_start_creates_nothing(self):
        self.stop.set()
        with self.assertRaises(app.Cancelled):
            app.transcribe_file(self.source, None, app.MODELS[0], 120, self.stop, lambda _: None)
        self.assertFalse(self.source.with_suffix('').exists())

    def test_errors_do_not_reveal_raw_content(self):
        self.assertNotIn('private', app.safe_error(RuntimeError('private')))
        error = RuntimeError('private')
        error.status_code = 401
        self.assertIn('APIキー', app.safe_error(error))
        error.status_code = 429
        self.assertIn('利用上限', app.safe_error(error))

    def test_missing_ffmpeg(self):
        with patch.object(app.shutil, 'which', return_value=None), self.assertRaises(app.UserError):
            app.split_audio(self.source, self.folder, 120, self.stop)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
    def test_real_ffmpeg_synthetic_audio(self):
        self.source.unlink()
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=2.4', '-c:a', 'aac', str(self.source)], check=True)
        chunks = self.folder / 'chunks'
        chunks.mkdir()
        result = app.split_audio(self.source, chunks, 1, self.stop)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(0 < p.stat().st_size < 24000 for p in result))


if __name__ == '__main__':
    unittest.main()
