"""Verify pre-action accounting, labels, partitions, and hidden-card independence."""
import json
from pathlib import Path
import tempfile
import unittest
from poker_bot.data import extract_decisions, replay_record

HAND = """[1]
variant = 'NT'
ante_trimming_status = false
antes = [0, 0]
blinds_or_straddles = [1, 2]
min_bet = 2
starting_stacks = [100, 100]
actions = ['d dh p1 AsKs', 'd dh p2 QhJh', 'p2 cbr 6', 'p1 cc', 'd db 2c3d4h', 'p1 cbr 4', 'p2 f']
venue = 'synthetic'
players = ['a', 'b']
hand = 1
table = 'test'
year = 2009
month = 7
day = 1
time = 12:00:00
"""


class DecisionTests(unittest.TestCase):
    def extract(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'sample.phhs'
            source.write_text(text)
            output = Path(tmp) / 'rows'
            report = extract_decisions(source, output)
            self.assertEqual(report['failures'], [])
            rows = [json.loads(line) for line in (output / 'decisions.jsonl').read_text().splitlines()]
            partition_rows = []
            for label in ('call', 'fold', 'raise'):
                for path in (output / label).glob('*.jsonl'):
                    partition_rows.extend(json.loads(line) for line in path.read_text().splitlines())
            self.assertEqual(sorted(rows, key=lambda r: r['decision_index']),
                             sorted(partition_rows, key=lambda r: r['decision_index']))
            return rows

    def report_for(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'sample.phhs'
            source.write_text(text)
            return extract_decisions(source, Path(tmp) / 'rows')

    def test_duplicate_copies_exported_once(self):
        conflict = HAND.replace('p2 cbr 6', 'p2 cbr 8')
        report = self.report_for(HAND + HAND + conflict)
        self.assertEqual(report['counts']['hands_exported'], 1)
        self.assertEqual(report['counts']['exact_duplicates_skipped'], 1)
        self.assertEqual(report['counts']['conflicting_copies_skipped'], 1)
        self.assertEqual(report['rows'], 3)

    def test_invalid_first_copy_does_not_block_valid_copy(self):
        invalid = HAND.replace('year = 2009\n', '')
        report = self.report_for(invalid + HAND)
        self.assertEqual(report['counts']['hands_failed'], 1)
        self.assertEqual(report['counts']['hands_exported'], 1)
        self.assertEqual(report['rows'], 3)

    def test_inserted_check_discards_whole_hand(self):
        missing_check = HAND.replace("'p1 cbr 4', 'p2 f'", "'p2 cbr 4', 'p1 f'")
        report = self.report_for(missing_check)
        self.assertEqual(report['counts']['hands_with_inserted_decisions'], 1)
        self.assertEqual(report['rows'], 0)
        self.assertIn('unrecorded', report['failures'][0]['error'])

    def test_optional_metadata_not_required(self):
        rows = self.extract(HAND.replace("table = 'test'\n", ''))
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[0]['table'])

    def test_unknown_board_discards_hand(self):
        report = self.report_for(HAND.replace('2c3d4h', '??????'))
        self.assertEqual(report['rows'], 0)
        self.assertEqual(report['counts']['hands_failed'], 1)

    def test_replay_captures_metadata_warnings(self):
        raw = HAND.replace('[1]\n', '').replace("venue = 'synthetic'", "venue = 'synthetic'\ntime_zone_abbreviation = 'ET'")
        _, _, warnings = replay_record(raw.encode())
        self.assertEqual(sum(warnings.values()), 1)
        self.assertIn('time_zone_abbreviation', next(iter(warnings)))

    def test_before_action_amounts_and_streets(self):
        rows = self.extract(HAND)
        self.assertEqual([r['label'] for r in rows], ['raise', 'call', 'fold'])
        self.assertEqual([r['street'] for r in rows], ['preflop', 'preflop', 'flop'])
        self.assertEqual([r['pot'] for r in rows], [3, 8, 16])
        self.assertEqual([r['amount_to_call'] for r in rows], [1, 4, 4])
        self.assertEqual([r['actor_stack'] for r in rows], [99, 98, 94])
        self.assertEqual(rows[0]['prior_betting_actions'], [])
        self.assertEqual(rows[1]['prior_betting_actions'], ['p2 cbr 6'])
        self.assertEqual(rows[0]['board'], [])
        self.assertEqual(rows[2]['board'], ['2c', '3d', '4h'])
        self.assertEqual(rows[0]['position'], 'button_small_blind')
        self.assertTrue(all(r['amount_to_call'] > 0 for r in rows))

    def test_hidden_cards_do_not_change_features(self):
        first = self.extract(HAND)
        second = self.extract(HAND.replace('AsKs', '????').replace('QhJh', '????'))
        self.assertEqual(first, second)
