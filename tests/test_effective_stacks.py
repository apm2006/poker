"""Actor-risk semantics and non-destructive derived-output checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pokerkit import HandHistory
from poker_bot.data import correct_effective_stacks, extract_decisions
from poker_bot.features import decision_snapshot
from test_features import HAND


class EffectiveStackTests(unittest.TestCase):
    def test_formula_matches_engine_with_pending_bets_and_all_ins(self):
        for stacks in ([100, 100], [50, 100], [200, 100]):
            with self.subTest(stacks=stacks):
                raw = HAND.split('\n', 1)[1]
                raw = raw.replace('starting_stacks = [100, 100]', f'starting_stacks = {stacks}')
                old = "['d dh p1 AsKs', 'd dh p2 QhJh', 'p2 cbr 6', 'p1 cc', 'd db 2c3d4h', 'p1 cbr 4', 'p2 f']"
                raw = raw.replace(old, "['d dh p1 AsKs', 'd dh p2 QhJh', 'p2 cbr 100', 'p1 f']")
                history = HandHistory.loads(raw)
                saw_all_in = False
                for state in history:
                    actor = state.actor_index
                    if actor is None or not state.checking_or_calling_amount:
                        continue
                    snapshot = decision_snapshot(state, history, [])
                    expected = min(state.stacks[actor], state.stacks[1-actor] + state.checking_or_calling_amount)
                    self.assertEqual(snapshot['effective_stack'], expected)
                    self.assertEqual(snapshot['effective_stack_over_pot'], expected / state.total_pot_amount)
                    if state.stacks[1-actor] == 0:
                        saw_all_in = True
                        self.assertEqual(expected, min(stacks[0] - 2, 98))
                        self.assertGreater(expected, 0)
                self.assertTrue(saw_all_in)

    def test_derived_copy_changes_only_approved_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            phh = root / 'source.phhs'
            phh.write_text(HAND)
            extract_decisions(phh, source)
            original = []
            for line in (source / 'decisions.jsonl').read_text().splitlines():
                row = json.loads(line)
                row['effective_stack'] = min(row['actor_stack'], row['opponent_stack'])
                row['effective_stack_over_pot'] = row['effective_stack'] / row['pot']
                original.append(row)
            path = source / 'decisions.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in original))
            before = path.read_bytes()
            summary = source / 'summary.json'
            report = json.loads(summary.read_text())
            report['status'] = 'complete'
            summary.write_text(json.dumps(report))
            output = root / 'corrected'
            with patch('poker_bot.data.replay_record', side_effect=AssertionError('must not replay')):
                result = correct_effective_stacks(source, output)
            self.assertEqual(before, path.read_bytes())
            rows = [json.loads(line) for line in (output / 'decisions.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 3)
            self.assertEqual(result['counts']['effective_stack_changed'], 3)
            for old, new in zip(original, rows):
                expected = min(old['actor_stack'], old['opponent_stack'] + old['amount_to_call'])
                self.assertEqual(new['effective_stack'], expected)
                self.assertEqual(new['effective_stack_over_pot'], expected / old['pot'])
                for field in old.keys() - {'effective_stack', 'effective_stack_over_pot'}:
                    self.assertEqual(old[field], new[field])
            self.assertEqual(sum(len(p.read_text().splitlines()) for p in output.glob('*/*.jsonl')), 3)
            with self.assertRaises(FileExistsError):
                correct_effective_stacks(source, output)
            report['rows'] = 999
            summary.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'row count'):
                correct_effective_stacks(source, root / 'bad')
            self.assertFalse((root / 'bad').exists())
