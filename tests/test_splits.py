"""Approved temporal boundaries, expanding folds, ties, and source preservation."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from poker_bot.evaluation import create_temporal_splits


class SplitTests(unittest.TestCase):
    def test_boundaries_ties_and_folds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            rows = []
            stamps = ['2009-07-08T23:59:59.000000Z','2009-07-09T00:00:00.000000Z',
                      '2009-07-09T00:00:00.000000Z','2009-07-12T00:00:00.000000Z',
                      '2009-07-15T00:00:00.000000Z','2009-07-18T00:00:00.000000Z']
            for index, stamp in enumerate(stamps):
                for decision in [0,1]:
                    rows.append({'timestamp_utc':stamp,'source_file':'a','record_index':index,
                                 'decision_index':decision,'site':'test','street':'preflop','label':'call'})
            raw = ''.join(json.dumps(r)+'\n' for r in rows).encode()
            (source/'decisions.jsonl').write_bytes(raw)
            manifest = {'status':'complete','counts':{'resolved_rows':len(rows)},'decisions_sha256':hashlib.sha256(raw).hexdigest()}
            (source/'summary.json').write_text(json.dumps(manifest))
            output = root / 'splits'
            report = create_temporal_splits(source,output)
            self.assertEqual(report['rows'],12)
            self.assertEqual(report['blocks']['validation_1']['rows'],4)
            self.assertEqual([r['training_rows'] for r in report['folds']],[2,6,8])
            self.assertEqual(report['folds'][2]['train_files'],['initial_training.jsonl','validation_1.jsonl','validation_2.jsonl'])
            combined = b''.join((output / v['file']).read_bytes() for v in report['blocks'].values())
            self.assertEqual(combined,raw)
            self.assertEqual((source/'decisions.jsonl').read_bytes(),raw)
            self.assertNotIn('final_test.jsonl',report['final_refit_files'])
            with self.assertRaises(FileExistsError):create_temporal_splits(source,output)
            manifest['decisions_sha256']='wrong'
            (source/'summary.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'count/hash'):
                create_temporal_splits(source,root/'bad')
            self.assertFalse((root/'bad').exists())
