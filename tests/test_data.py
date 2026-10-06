"""Check initial-player filtering and candidate identity accounting."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from poker_bot.data import audit_zip, literal


def hand(number, count=2, ante=0, unknown=True):
    return '\n'.join([
        f'[{number}]', "variant = 'NT'", f'starting_stacks = {[100] * count}',
        f'antes = {[ante] * count}', f'blinds_or_straddles = {[1, 2] + [0] * (count - 2)}',
        f'players = {[str(i) for i in range(count)]}', f'seats = {list(range(count))}',
        f'winnings = {[0] * count}',
        f"actions = {['d dh p1 ????' if unknown else 'd dh p1 AsKs', 'p1 f']!r}",
        "venue = 'test'", f'hand = {number}', "table = 'test'",
        'year = 2009', 'month = 7', 'day = 1', 'time = 12:00:00', '',
    ])


class AuditTests(unittest.TestCase):
    def test_phh_nonfinite_values(self):
        import math
        stacks = literal({"starting_stacks": "[inf, inf]"}, "starting_stacks")
        self.assertTrue(all(math.isinf(x) for x in stacks))

    def test_nonfinite_stacks_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'source.zip'
            entries = [hand(1)]
            for number, stacks in enumerate(('[inf, inf]', '[100, inf]', '[nan, 100]', '[-inf, 100]'), 2):
                entries.append(hand(number).replace('[100, 100]', stacks, 1))
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('data/handhq/sample.phhs', ''.join(entries))
            counts = audit_zip(archive, Path(tmp) / 'audit.json')['counts']
            self.assertEqual(counts['two_player_no_limit'], 5)
            self.assertEqual(counts['heads_up_with_nonfinite_stacks'], 4)
            self.assertEqual(counts['unique_structural_candidates'], 1)
            self.assertNotIn('parse_or_structure_errors', counts)

    def test_filter_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'source.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('data/handhq/sample.phhs', hand(1) + hand(2, 6) + hand(3, ante=1) + hand(1) + hand(1, unknown=False))
                z.writestr('data/pluribus/ignored.phhs', hand(9))
            report = audit_zip(archive, Path(tmp) / 'audit.json')
            counts = report['counts']
            self.assertEqual(counts['human_records'], 5)
            self.assertEqual(counts['not_two_starting_players'], 1)
            self.assertEqual(counts['heads_up_with_antes'], 1)
            self.assertEqual(counts['unique_structural_candidates'], 1)
            self.assertEqual(counts['exact_duplicate_candidates'], 1)
            self.assertEqual(counts['conflicting_identity_candidates'], 1)
            self.assertEqual(counts['candidates_with_unknown_hole_cards'], 1)
            self.assertEqual(json.loads((Path(tmp) / 'audit.json').read_text())['counts'], counts)


if __name__ == '__main__':
    unittest.main()
