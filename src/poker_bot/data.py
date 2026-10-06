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
