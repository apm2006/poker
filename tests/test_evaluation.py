"""Date profiling and half-open period coverage without random reassignment."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from poker_bot.evaluation import profile_dates, period_coverage


class CoverageTests(unittest.TestCase):
    def test_utc_grouping_and_whole_hand_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for day, hand, decision, label in [('01',1,0,'raise'),('01',1,1,'call'),('02',2,0,'fold')]:
                rows.append({'timestamp_utc':f'2009-07-{day}T00:00:00.000000Z',
                             'source_file':'a','record_index':hand,'decision_index':decision,
                             'label':label,'street':'preflop','site':'test'})
            raw = ''.join(json.dumps(r)+'\n' for r in rows).encode()
            (root/'decisions.jsonl').write_bytes(raw)
            (root/'summary.json').write_text(json.dumps({'status':'complete','counts':{'resolved_rows':3},
                'decisions_sha256':hashlib.sha256(raw).hexdigest()}))
            report = profile_dates(root,root/'profile.json')
            period = period_coverage(report['days'],'2009-07-01','2009-07-02')
            self.assertEqual(period['rows'],2)
            self.assertEqual(period['hands'],1)
            self.assertEqual(period['actions'],{'raise':1,'call':1})
            self.assertEqual(report['days']['2009-07-02']['hands'],1)
            (root/'decisions.jsonl').write_bytes(b''.join(line+b'\n' for line in raw.splitlines()[::-1]))
            with self.assertRaisesRegex(ValueError,'order'):
                profile_dates(root,root/'bad.json')
            self.assertFalse((root/'bad.json').exists())
