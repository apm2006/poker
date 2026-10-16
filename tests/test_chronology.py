"""Timezone conversion, disk sorting, ties, and source preservation."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from poker_bot.chronology import normalize_and_sort, utc_timestamp


class ChronologyTests(unittest.TestCase):
    def test_known_offsets_and_midnight(self):
        for label, local in [('ET','12:00:00'),('EDT','12:00:00'),('CEST','18:00:00'),('ICT','23:00:00')]:
            self.assertEqual(utc_timestamp('2009-07-01',local,label), '2009-07-01T16:00:00.000000Z')
        self.assertEqual(utc_timestamp('2009-07-01','00:30:00','CEST'), '2009-06-30T22:30:00.000000Z')
        self.assertIsNone(utc_timestamp('2009-07-01','12:00:00','GMT-0910'))
        self.assertIsNone(utc_timestamp('2009-07-01','12:00:00',None))

    def test_ambiguous_time_not_guessed(self):
        with self.assertRaises(ValueError):
            utc_timestamp('2009-11-01','01:30:00','ET')
        with self.assertRaises(ValueError):
            utc_timestamp('2009-03-08','02:30:00','ET')

    def test_sorting_partitions_and_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            metadata = root / 'metadata.sqlite'
            entries = [('a','12:00:00','ET'),('b','17:00:00','CEST'),('c','22:00:00','ICT'),('d','12:00:00','GMT-0910')]
            rows = []
            with sqlite3.connect(metadata) as db:
                db.execute('CREATE TABLE hands(source_file TEXT,record_index INT,site TEXT,hand TEXT,date TEXT,time TEXT,timezone TEXT)')
                for name, time, label in entries:
                    db.execute('INSERT INTO hands VALUES (?,?,?,?,?,?,?)',(name,1,'test',name,'2009-07-01',time,label))
                    for decision in ([2,0] if name=='a' else [0]):
                        rows.append({'source_file':name,'record_index':1,'site':'test','hand_id':name,
                                     'date':'2009-07-01','time':time,'decision_index':decision,
                                     'label':'call','street':'preflop','effective_stack':98.0})
            data = ''.join(json.dumps(r)+'\n' for r in rows).encode()
            (source/'decisions.jsonl').write_bytes(data)
            (source/'summary.json').write_text(json.dumps({'status':'complete','counts':{'rows':5},'decisions_sha256':hashlib.sha256(data).hexdigest()}))
            output = root / 'sorted'
            report = normalize_and_sort(source,metadata,output)
            self.assertEqual(report['counts']['resolved_rows'],4)
            self.assertEqual(report['counts']['unresolved_rows'],1)
            self.assertEqual(report['counts']['equal_timestamp_hand_groups'],1)
            result = [json.loads(line) for line in (output/'decisions.jsonl').read_text().splitlines()]
            self.assertEqual([(r['hand_id'],r['decision_index']) for r in result],[('b',0),('c',0),('a',0),('a',2)])
            unresolved = json.loads((output/'unresolved-timezones.jsonl').read_text())
            self.assertIsNone(unresolved['timestamp_utc'])
            self.assertEqual(unresolved['raw_timezone'],'GMT-0910')
            self.assertEqual((source/'decisions.jsonl').read_bytes(),data)
            for r in result + [unresolved]:
                original = next(old for old in rows if (old['hand_id'],old['decision_index'])==(r['hand_id'],r['decision_index']))
                for k,v in original.items():
                    self.assertEqual(r[k],v)
            self.assertEqual((output/'call/preflop.jsonl').read_bytes(),(output/'decisions.jsonl').read_bytes())
            with self.assertRaises(FileExistsError):
                normalize_and_sort(source,metadata,output)
            with sqlite3.connect(metadata) as db:
                db.execute("UPDATE hands SET date='2009-07-02' WHERE source_file='a'")
            with self.assertRaisesRegex(ValueError,'does not match'):
                normalize_and_sort(source,metadata,root/'bad')
            self.assertFalse((root/'bad').exists())
