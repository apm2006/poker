"""Verify resume, deduplication, invalidation, and crash recovery with real replay."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from poker_bot import cache
from test_features import HAND


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root / 'hands.zip'
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('data/handhq/test/1.phhs', HAND)
            z.writestr('data/handhq/test/2.phhs', HAND + HAND.replace('hand = 1', 'hand = 2'))
        self.output = self.root / 'export'

    def run_export(self, **kwargs):
        return cache.export_cached(self.archive, self.output, **kwargs)

    def test_resume_and_duplicate_tracking(self):
        first = self.run_export(max_files=1)
        self.assertFalse(first['full_archive'])
        with patch.object(cache, 'replay_record', wraps=cache.replay_record) as replay:
            second = self.run_export()
        self.assertEqual(replay.call_count, 1)  # duplicate reuses its cached outcome
        self.assertEqual(second['this_run']['files_reused'], 1)
        self.assertEqual(second['this_run']['record_cache_hits'], 1)
        self.assertEqual(second['counts']['hands_retained'], 2)
        self.assertEqual(second['counts']['exact_duplicates_skipped'], 1)
        canonical = Path(second['output_dir']) / 'decisions.jsonl'
        before = canonical.read_bytes()
        with patch.object(cache, 'replay_record', side_effect=AssertionError('must use cache')):
            third = self.run_export()
        self.assertEqual(third['this_run']['files_reused'], 2)
        self.assertEqual(before, canonical.read_bytes())
        rows = [json.loads(line) for line in before.splitlines()]
        self.assertEqual(len(rows), 6)
        parts = list(Path(third['output_dir']).glob('*/*.jsonl'))
        parts = [p for p in parts if p.parent.name != 'chunks']
        self.assertEqual(sum(len(p.read_text().splitlines()) for p in parts), 6)

    def test_interrupted_chunk_does_not_reserve_identity(self):
        original = cache.durable_replace
        def crash_after_chunk(temp, final):
            original(temp, final)
            if final.parent.name == 'chunks':
                raise RuntimeError('simulated crash after rename before commit')
        with patch.object(cache, 'durable_replace', side_effect=crash_after_chunk):
            with self.assertRaisesRegex(RuntimeError, 'simulated crash'):
                self.run_export()
        recovered = self.run_export()
        self.assertEqual(recovered['counts']['hands_retained'], 2)
        self.assertEqual(recovered['counts']['rows'], 6)

    def test_invalid_first_copy_allows_valid_later_copy(self):
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('data/handhq/test/1.phhs', HAND.replace('year = 2009\n', ''))
            z.writestr('data/handhq/test/2.phhs', HAND)
        report = self.run_export()
        self.assertEqual(report['counts']['hands_rejected'], 1)
        self.assertEqual(report['counts']['hands_retained'], 1)
        self.assertEqual(len((Path(report['output_dir']) / 'rejections.jsonl').read_text().splitlines()), 1)

    def test_rejected_record_is_cached(self):
        invalid = HAND.replace('year = 2009\n', '')
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('data/handhq/test/1.phhs', invalid)
            z.writestr('data/handhq/test/2.phhs', invalid + HAND)
        with patch.object(cache, 'replay_record', wraps=cache.replay_record) as replay:
            report = self.run_export()
        self.assertEqual(replay.call_count, 2)
        self.assertEqual(report['this_run']['record_cache_hits'], 1)
        self.assertEqual(report['counts']['hands_rejected'], 2)

    def test_interrupted_final_views_rebuild_from_chunks(self):
        original = cache.durable_replace
        def crash_during_views(temp, final):
            original(temp, final)
            if final.name == 'decisions.jsonl':
                raise RuntimeError('interrupted assembly')
        with patch.object(cache, 'durable_replace', side_effect=crash_during_views):
            with self.assertRaisesRegex(RuntimeError, 'interrupted assembly'):
                self.run_export()
        marker = next(self.output.glob('*/*/summary.json'))
        self.assertEqual(json.loads(marker.read_text())['status'], 'building')
        with patch.object(cache, 'replay_record', side_effect=AssertionError('must use chunks')):
            recovered = self.run_export()
        self.assertEqual(recovered['status'], 'complete')
        self.assertEqual(recovered['this_run']['files_reused'], 2)
        self.assertEqual(recovered['counts']['rows'], 6)

    def test_version_change_creates_separate_cache(self):
        first = self.run_export()
        with patch.object(cache, 'processing_version', return_value=('new-version', {'schema': 2})):
            second = self.run_export()
        self.assertNotEqual(first['output_dir'], second['output_dir'])
        self.assertEqual(second['this_run']['files_processed'], 2)

    def test_archive_change_creates_separate_cache(self):
        first = self.run_export()
        with zipfile.ZipFile(self.archive, 'a') as z:
            z.writestr('extra.txt', 'changed source')
        second = self.run_export()
        self.assertNotEqual(first['output_dir'], second['output_dir'])

    def test_corrupt_chunk_is_detected(self):
        first = self.run_export()
        chunk = next((Path(first['output_dir']) / 'chunks').glob('*.jsonl'))
        chunk.write_text('broken')
        with self.assertRaisesRegex(RuntimeError, 'missing or damaged'):
            self.run_export()
