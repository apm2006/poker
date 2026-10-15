"""Read-only structural audit of human PHH records in the source ZIP.

Eligibility here is preliminary: legal replay, terminal-state validation, and
sustained heads-up session classification require further implementation.
"""

import ast
from collections import Counter
import hashlib
import json
import math
import tomllib
from pathlib import Path
import sqlite3
import tempfile
import zipfile


def records(stream):
    """Yield individual records without extracting the archive."""
    lines = []
    for line in stream:
        if line.startswith(b'[') and line.rstrip().endswith(b']'):
            if lines:
                yield b''.join(lines)
            lines = []
        elif line.strip():
            lines.append(line)
    if lines:
        yield b''.join(lines)


def fields(record):
    result = {}
    for line in record.decode('utf-8').splitlines():
        key, sep, value = line.partition(' = ')
        if sep:
            result[key] = value
    return result


def literal(values, key):
    try:
        return ast.literal_eval(values[key])
    except (ValueError, SyntaxError):
        return tomllib.loads('value = ' + values[key])['value']


def audit_zip(archive, output):
    counts = Counter()
    player_counts = Counter()
    sites = Counter()
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(archive) as source:
        db = sqlite3.connect(str(Path(tmp) / 'identities.sqlite'))
        db.execute('CREATE TABLE hands (site TEXT, hand TEXT, digest TEXT, PRIMARY KEY(site, hand))')
        files = [n for n in source.namelist() if '/handhq/' in n and n.endswith('.phhs')]
        for index, name in enumerate(files, 1):
            with source.open(name) as stream:
                for record in records(stream):
                    counts['human_records'] += 1
                    try:
                        values = fields(record)
                        stack_text = values['starting_stacks']
                        count = len(stack_text.strip('[]').split(','))
                        player_counts[count] += 1
                        if literal(values, 'variant') != 'NT':
                            counts['other_variant'] += 1
                            continue
                        if count != 2:
                            counts['not_two_starting_players'] += 1
                            continue
                        counts['two_player_no_limit'] += 1
                        stacks = literal(values, 'starting_stacks')
                        if not all(math.isfinite(x) for x in stacks):
                            counts['heads_up_with_nonfinite_stacks'] += 1
                            continue
                        blinds = literal(values, 'blinds_or_straddles')
                        antes = literal(values, 'antes')
                        if any(antes):
                            counts['heads_up_with_antes'] += 1
                            continue
                        if len(blinds) != 2 or min(blinds) <= 0 or max(blinds) != 2 * min(blinds):
                            counts['heads_up_nonstandard_blinds'] += 1
                            continue
                        actions = literal(values, 'actions')
                        players = literal(values, 'players')
                        seats = literal(values, 'seats')
                        winnings = literal(values, 'winnings')
                        if (len(players) != 2 or len(set(players)) != 2 or len(seats) != 2
                                or len(winnings) != 2 or not actions or min(stacks) <= 0):
                            counts['heads_up_invalid_structure'] += 1
                            continue
                        for key in ('table', 'year', 'month', 'day', 'time'):
                            if key not in values:
                                raise ValueError('missing metadata')
                        site = literal(values, 'venue')
                        hand = str(literal(values, 'hand'))
                        digest = hashlib.sha256(record).hexdigest()
                        existing = db.execute('SELECT digest FROM hands WHERE site=? AND hand=?', (site, hand)).fetchone()
                        if existing:
                            counts['exact_duplicate_candidates' if existing[0] == digest else 'conflicting_identity_candidates'] += 1
                            continue
                        db.execute('INSERT INTO hands VALUES (?, ?, ?)', (site, hand, digest))
                        counts['unique_structural_candidates'] += 1
                        sites[site] += 1
                        if any('????' in a for a in actions):
                            counts['candidates_with_unknown_hole_cards'] += 1
                    except (ValueError, SyntaxError, KeyError, TypeError, UnicodeError):
                        counts['parse_or_structure_errors'] += 1
            if index % 500 == 0:
                db.commit()
                print(f'Audited {index}/{len(files)} files; {counts["human_records"]:,} records', flush=True)
        db.commit()
        db.close()
    report = {
        'archive': str(Path(archive).resolve()), 'human_files': len(files),
        'counts': dict(counts), 'starting_player_counts': dict(sorted(player_counts.items())),
        'candidate_counts_by_site': dict(sites),
        'limitations': [
            'Structural candidates are not yet validated by a poker engine for legal actions or completed hands.',
            'Conflicting identities are counted; the first record remains a preliminary candidate, not an approved training example.',
            'Session continuity and anonymized player identity consistency are not yet assessed.',
            'Some structurally flagged records lack winnings metadata; these flags do not establish that the underlying hands are corrupt.',
            'Hands with any nonfinite starting stack are excluded from candidates; values are not imputed.',
            'Standard blinds are provisionally identified as two positive blinds with a 1:2 ratio; unusual forced posts need replay validation.',
            'Duplicate content comparison uses raw record bytes; semantic equivalents with different formatting can appear as conflicts.',
        ],
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    return report


def replay_record(raw):
    """Validate a single record and return bounded per-hand rows and diagnostics."""
    from pokerkit import HandHistory
    from .features import decision_snapshot
    import warnings
    from datetime import date, time

    hand_rows = []
    prior_actions = []
    counts = Counter()
    warning_counts = Counter()
    with warnings.catch_warnings(record=True) as observed:
        warnings.simplefilter('always')
        history = HandHistory.loads(raw.decode())
        if history.variant != 'NT' or len(history.starting_stacks) != 2:
            raise ValueError('Expected heads-up no-limit Holdem')
        if not all(math.isfinite(x) and x > 0 for x in history.starting_stacks):
            raise ValueError('Expected finite positive starting stacks')
        if not history.venue or history.hand is None:
            raise ValueError('Missing site/hand identity needed for deduplication')
        # Missing optional metadata (table, winnings, seats) is allowed.
        date_value = date(history.year, history.month, history.day).isoformat()
        if not isinstance(history.time, time):
            raise ValueError('Missing time needed for chronological splitting')
        if any(not math.isfinite(x) or x != 0 for x in history.antes):
            raise ValueError('Expected zero antes')
        blinds = history.blinds_or_straddles
        if (blinds is None or len(blinds) != 2
                or not all(math.isfinite(x) and x > 0 for x in blinds)
                or max(blinds) != 2 * min(blinds)):
            raise ValueError('Expected standard small/big blinds')
        if history.min_bet is None or not math.isfinite(history.min_bet) or history.min_bet <= 0:
            raise ValueError('Missing or invalid minimum bet')
        for action_text in history.actions:
            words = action_text.split('#', 1)[0].split()
            if len(words) >= 2 and words[1] == 'cbr':
                if len(words) != 3 or not math.isfinite(history.parse_value(words[2])):
                    raise ValueError('Missing or nonfinite bet amount')
        before = None
        last = None
        operation_count = 0
        for state, action in history.state_actions:
            if action is None:
                inferred = sum(
                    type(op).__name__ in ("Folding", "CheckingOrCalling", "CompletionBettingOrRaisingTo")
                    for op in state.operations[operation_count:]
                )
                if inferred:
                    counts['inferred_betting_actions'] += inferred
                    counts['hands_with_inserted_decisions'] += 1
                    raise ValueError('Replay inserted an unrecorded player decision')
            operation_count = len(state.operations)
            last = state
            words = action.split('#', 1)[0].split() if action else []
            if len(words) >= 2 and words[1] in ('f', 'cc', 'cbr'):
                actor = int(words[0][1:]) - 1
                if before is None or before['actor_index'] != actor:
                    raise ValueError('Recorded action does not match preceding actor')
                if before['amount_to_call'] > 0:
                    label = {'f': 'fold', 'cc': 'call', 'cbr': 'raise'}[words[1]]
                    hand_rows.append({
                        'hand_id': history.hand,
                        'site': history.venue, 'table': history.table,
                        'player_id': history.players[actor] if history.players else None,
                        'date': date_value,
                        'time': str(history.time),
                        'decision_index': len(prior_actions),
                        **before, 'label': label,
                    })
                else:
                    counts['actions_not_facing_bet'] += 1
                prior_actions.append(' '.join(words))
            before = decision_snapshot(state, history, prior_actions)
            if before is not None:
                if any('?' in card for card in before['board']):
                    raise ValueError('Unknown board cards needed for decision reconstruction')
                for key in ('pot', 'amount_to_call', 'actor_stack', 'opponent_stack'):
                    if not math.isfinite(before[key]) or before[key] < 0:
                        raise ValueError('Invalid reconstructed chip amount')
        if last is None or last.status:
            raise ValueError('Hand did not reach completion')
    for warning in observed:
        warning_counts[str(warning.message)] += 1
    return hand_rows, dict(counts), dict(warning_counts)


def extract_decisions(sample_path, output_dir):
    """Export validated sample decisions, keeping the first valid copy per site/hand."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    failures = []
    counts = Counter()
    warning_counts = Counter()
    seen = {}
    with Path(sample_path).open('rb') as stream:
        for record_index, raw in enumerate(records(stream), 1):
            try:
                values = fields(raw)
                identity = (literal(values, 'venue'), str(literal(values, 'hand')))
                digest = hashlib.sha256(raw).hexdigest()
                if identity in seen:
                    counts['exact_duplicates_skipped' if seen[identity] == digest else 'conflicting_copies_skipped'] += 1
                    continue
                hand_rows, hand_counts, hand_warnings = replay_record(raw)
                counts.update(hand_counts)
                warning_counts.update(hand_warnings)
                for row in hand_rows:
                    row['record_index'] = record_index
                seen[identity] = digest
                rows.extend(hand_rows)
                counts['hands_exported'] += 1
            except Exception as exc:
                if 'unrecorded player decision' in str(exc):
                    counts['hands_with_inserted_decisions'] += 1
                failures.append({'record_index': record_index, 'error': f'{type(exc).__name__}: {exc}'})
                counts['hands_failed'] += 1
    # One canonical file; partitions are identical inspection views, not extra samples.
    def write_rows(path, selected):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w') as stream:
            for row in selected:
                stream.write(json.dumps(row, allow_nan=False) + '\n')

    write_rows(output_dir / 'decisions.jsonl', rows)
    partitions = {}
    for label in ('fold', 'call', 'raise'):
        partitions[label] = {}
        for street in ('preflop', 'flop', 'turn', 'river'):
            selected = [r for r in rows if r['label'] == label and r['street'] == street]
            write_rows(output_dir / label / f'{street}.jsonl', selected)
            partitions[label][street] = len(selected)
    report = {'input': str(sample_path), 'counts': dict(counts), 'rows': len(rows),
              'partitions': partitions, 'warnings': dict(warning_counts), 'failures': failures,
              'limitations': [
                  'Sample export only; deduplicated by site/hand, but not session-classified training data.',
                  'Hands requiring inserted betting decisions are discarded; bookkeeping and hidden-card placeholders are permitted.',
                  'Missing optional metadata is permitted; a valid date/time and site/hand identity are required.',
                  'Player-history tendencies and board-texture encodings are not implemented.',
                  'Partitions duplicate the canonical rows; never concatenate them with decisions.jsonl.',
                  'Player/site/hand/time identifiers are provenance, not approved model inputs.',
              ]}
    (output_dir / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
