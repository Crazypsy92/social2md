import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from social2md_app.bilibili import BilibiliAdapter, access_error, canonical_url
from social2md_app.bilibili_runner import item_metadata, run_bilibili
from social2md_app.cli import _make_parser
from social2md_app.state import TaskState
from social2md_app.storage import StorageLimitExceeded
from social2md_app.video import process_video


class BilibiliTests(unittest.TestCase):
    def test_canonical_space_and_part_urls(self):
        self.assertEqual(canonical_url('https://space.bilibili.com/123?spm_id_from=test'),
                         'https://space.bilibili.com/123/video')
        self.assertEqual(canonical_url('https://www.bilibili.com/video/BV123?p=2&tracking=x'),
                         'https://www.bilibili.com/video/BV123?p=2')
        for url in ['https://bilibili.com.example/video/BV123', 'https://space.bilibili.com/abc',
                    'file:///video/BV123']:
            with self.assertRaises(ValueError):
                canonical_url(url)

    def test_part_identifiers_are_distinct(self):
        first = item_metadata({'id': 'BV123_p1', 'webpage_url': 'https://www.bilibili.com/video/BV123?p=1'})
        second = item_metadata({'id': 'BV123_p2', 'webpage_url': 'https://www.bilibili.com/video/BV123?p=2'})
        self.assertNotEqual(first['content_id'], second['content_id'])
        with self.assertRaises(ValueError):
            item_metadata({'id': '../escape', 'webpage_url': first['source_url']})

    def test_lazy_playlist_traverses_all_pages_and_parts(self):
        adapter = BilibiliAdapter()
        visited = []
        def entries():
            for index in range(61):
                visited.append(index)
                yield {'id': str(index)}
        flattened = adapter._flatten({'_type': 'playlist', 'entries': entries()})
        self.assertEqual(visited, [])
        self.assertEqual(next(flattened)['id'], '0')
        self.assertEqual(visited, [0])
        self.assertEqual(len(list(flattened)), 60)

    def test_safe_error_does_not_echo_signed_urls(self):
        error = access_error(RuntimeError('Request failed (352) https://private/?token=secret'))
        self.assertIn('限流', error)
        self.assertNotIn('secret', error)

    def make_args(self, root):
        return _make_parser().parse_args([
            '-u', 'https://space.bilibili.com/123', '--keep-source',
            '--download-dir', str(root / 'videos'), '--out-dir', str(root / 'output'),
            '--state-dir', str(root / 'state'), '--export-dir', str(root / 'exports'),
        ])

    def test_sequential_processing_resume_quality_and_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.make_args(root)
            events = []
            infos = [{'id': f'BV123_p{i}', 'webpage_url': f'https://www.bilibili.com/video/BV123?p={i}',
                      'title': f'分 P {i}', 'description': '原文案', 'uploader': '测试作者'} for i in (1, 2)]
            def download(info, target, guard):
                events.append(('download', info['id']))
                target.write_bytes(b'x' * 2048)
                return target
            def process(video, out_dir, existing, model, language, **kwargs):
                events.append(('process', kwargs['source_metadata']['content_id']))
                metadata = kwargs['source_metadata']
                kwargs['output_path'].write_text(f"# {metadata['title']}\n\n## 原文案\n\n原文案\n\n## 口播转录\n\n测试转录内容。", encoding='utf-8')
                self.assertFalse(kwargs['delete_video'])
                return 'ok', {'title': metadata['title'], 'quality': {'avg_logprob': -0.1, 'max_compression': 1}}
            with patch('social2md_app.bilibili_runner.BilibiliAdapter') as adapter, \
                 patch('social2md_app.cli.is_valid_video', return_value=True), \
                 patch('social2md_app.cli.estimate_temp_bytes', return_value=0), \
                 patch('social2md_app.cli.process_video', side_effect=process):
                adapter.return_value.entries.side_effect = lambda _: iter([{'url': 'unused'}])
                adapter.return_value.resolve.side_effect = lambda _: iter(infos)
                adapter.return_value.download.side_effect = download
                self.assertEqual(run_bilibili(args), 0)
                self.assertEqual(events, [('download', 'BV123_p1'), ('process', 'BV123_p1'),
                                          ('download', 'BV123_p2'), ('process', 'BV123_p2')])
                self.assertEqual(run_bilibili(args), 0)
                self.assertEqual(len(events), 4)
            self.assertEqual(len(list((root / 'videos').glob('*.mkv'))), 2)
            with TaskState(next((root / 'state').glob('*.sqlite3'))) as state:
                self.assertEqual(state.status_counts('bilibili'), {'COMPLETED': 2})
                self.assertIsNotNone(state.get_meta('quality:BV123_p1'))
            import zipfile
            with zipfile.ZipFile(next((root / 'exports').glob('*.zip'))) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(sorted(archive.namelist()), ['BV123_p1.md', 'BV123_p2.md'])

    def test_listing_failure_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('social2md_app.bilibili_runner.BilibiliAdapter') as adapter:
                adapter.return_value.entries.side_effect = RuntimeError('Request rejected (352)')
                self.assertEqual(run_bilibili(self.make_args(root)), 1)
            with TaskState(next((root / 'state').glob('*.sqlite3'))) as state:
                self.assertEqual(state.get_meta('scan_complete'), '0')
                self.assertEqual(state.status_counts('bilibili'), {})

    def test_storage_pause_prevents_network_and_saves_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('social2md_app.bilibili_runner.BilibiliAdapter') as adapter, \
                 patch('social2md_app.bilibili_runner.StorageGuard.assert_can_start',
                       side_effect=StorageLimitExceeded('空间不足')):
                self.assertEqual(run_bilibili(self.make_args(root)), 75)
                adapter.assert_not_called()
            with TaskState(next((root / 'state').glob('*.sqlite3'))) as state:
                self.assertEqual(state.get_meta('paused'), '1')

    def test_markdown_preserves_platform_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / 'BV123_video.mkv'
            video.write_bytes(b'media')
            wav = root / 'audio.wav'
            wav.write_bytes(b'audio')
            metadata = {'title': '原始标题', 'description': '原始文案',
                        'source_url': 'https://www.bilibili.com/video/BV123', 'author': '作者'}
            with patch('social2md_app.video.extract_audio', return_value=wav), \
                 patch('social2md_app.video.transcribe', return_value=([], {'avg_logprob': -0.1})), \
                 patch('social2md_app.video.format_transcript', return_value='转录内容。'):
                result, _ = process_video(video, root, set(), 'small', 'zh', False, True,
                                          require_transcript=True, output_path=root / 'BV123.md',
                                          source_metadata=metadata)
            self.assertEqual(result, 'ok')
            content = (root / 'BV123.md').read_text()
            for expected in ['# 原始标题', '原始文案', metadata['source_url'], '作者', '转录内容。']:
                self.assertIn(expected, content)
            self.assertTrue(video.is_file())

    def test_processing_failure_retains_video_and_retries_from_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.make_args(root)
            info = {'id': 'BV123', 'webpage_url': 'https://www.bilibili.com/video/BV123'}
            def download(info, target, guard):
                target.write_bytes(b'x' * 2048)
                return target
            with patch('social2md_app.bilibili_runner.BilibiliAdapter') as adapter, \
                 patch('social2md_app.cli.is_valid_video', return_value=True), \
                 patch('social2md_app.cli.estimate_temp_bytes', return_value=0), \
                 patch('social2md_app.cli.process_video', return_value=('fail', None)):
                adapter.return_value.entries.side_effect = lambda _: iter([{}])
                adapter.return_value.resolve.side_effect = lambda _: iter([info])
                adapter.return_value.download.side_effect = download
                self.assertEqual(run_bilibili(args), 1)
                self.assertEqual(run_bilibili(args), 1)
                self.assertEqual(adapter.return_value.download.call_count, 1)
            self.assertTrue((root / 'videos/BV123_video.mkv').is_file())


if __name__ == '__main__':
    unittest.main()
