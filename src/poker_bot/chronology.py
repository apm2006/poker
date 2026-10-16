"""UTC normalization and disk-backed ordering of already validated decision rows."""

from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from zoneinfo import ZoneInfo


TIMEZONE_POLICY = {'ET': 'America/New_York', 'EDT': 'UTC-04:00',
                   'CEST': 'UTC+02:00', 'ICT': 'UTC+07:00'}


def utc_timestamp(date, time, label):
    """Return an aware UTC timestamp or None for unresolved source labels."""
    local = datetime.fromisoformat(f'{date}T{time}')
    if local.tzinfo is not None:
        raise ValueError('Expected a naive source timestamp plus a timezone label')
    if label == 'ET':
        zone = ZoneInfo('America/New_York')
        first, second = (local.replace(tzinfo=zone, fold=n) for n in (0, 1))
        if first.utcoffset() != second.utcoffset():
            raise ValueError('Ambiguous or nonexistent Eastern local time')
        aware = first
    elif label in ('EDT', 'CEST', 'ICT'):
        hours = {'EDT': -4, 'CEST': 2, 'ICT': 7}[label]
        aware = local.replace(tzinfo=timezone(timedelta(hours=hours)))
    else:
        return None
    return aware.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def normalize_and_sort(source_dir, metadata_path, output_dir):
    """Publish sorted resolved rows and a separate unresolved-timezone file.

    A temporary SQLite table performs the external sort. Original date/time,
    source identities, features, and labels remain intact. No history updates,
    timezone guesses, or train/test splits are performed.
    """
    source, metadata, destination = map(lambda p: Path(p).resolve(), (source_dir, metadata_path, output_dir))
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must be separate')
    if destination.exists():
        raise FileExistsError('Choose a new destination; existing output is never overwritten')
    summary = json.loads((source / 'summary.json').read_text())
    if summary.get('status') != 'complete':
        raise ValueError('Source export must be complete')
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts, partitions, labels = Counter(), Counter(), Counter()
    digest = hashlib.sha256()
    resolved_digest, unresolved_digest = hashlib.sha256(), hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix='.chronology-', dir=destination.parent) as work:
        work = Path(work)
        staging = work / 'output'
        staging.mkdir()
        with ExitStack() as stack:
            meta = sqlite3.connect(metadata.as_uri() + '?mode=ro', uri=True)
            stack.callback(meta.close)
            sorter = sqlite3.connect(work / 'sort.sqlite')
            stack.callback(sorter.close)
            sorter.execute('PRAGMA temp_store=FILE')
            sorter.execute('CREATE TABLE rows(utc TEXT,source TEXT,record INTEGER,decision INTEGER,payload TEXT, UNIQUE(source,record,decision))')
            unresolved = stack.enter_context((staging / 'unresolved-timezones.jsonl').open('wb'))
            current_source, lookup = None, {}
            current_hand, normalized, raw_label = None, None, None
            with (source / 'decisions.jsonl').open('rb') as stream:
                for raw in stream:
                    digest.update(raw)
                    row = json.loads(raw)
                    if row['source_file'] != current_source:
                        current_source = row['source_file']
                        lookup = {r[0]: r[1:] for r in meta.execute(
                            'SELECT record_index,site,hand,date,time,timezone FROM hands WHERE source_file=?', (current_source,))}
                    entry = lookup.get(row['record_index'])
                    if entry is None:
                        raise ValueError('Source hand is missing from audited timestamp metadata')
                    site, hand, date, time, label = entry
                    if (row['site'], str(row['hand_id']), row['date'], row['time']) != (site, hand, date, time):
                        raise ValueError('Timestamp metadata does not match source row')
                    key = current_source, row['record_index']
                    if key != current_hand:
                        current_hand = key
                        normalized = utc_timestamp(date, time, label)
                        raw_label = label
                        counts['resolved_hands' if normalized else 'unresolved_hands'] += 1
                        labels[str(label)] += 1
                    row.update(timestamp_utc=normalized, raw_timezone=raw_label,
                               timestamp_status='resolved' if normalized else 'unresolved_timezone')
                    payload = json.dumps(row, allow_nan=False)
                    counts['source_rows'] += 1
                    if normalized:
                        sorter.execute('INSERT INTO rows VALUES (?,?,?,?,?)',
                                       (normalized, current_source, row['record_index'], row['decision_index'], payload))
                        counts['resolved_rows'] += 1
                    else:
                        encoded = (payload + '\n').encode()
                        unresolved.write(encoded)
                        unresolved_digest.update(encoded)
                        counts['unresolved_rows'] += 1
                    if counts['source_rows'] % 100000 == 0:
                        sorter.commit()
                    if counts['source_rows'] % 1000000 == 0:
                        print(f'Normalized {counts["source_rows"]:,} rows', flush=True)
            sorter.commit()
            if counts['source_rows'] != summary['counts']['rows']:
                raise ValueError('Source row count does not match manifest')
            if summary.get('decisions_sha256') and digest.hexdigest() != summary['decisions_sha256']:
                raise ValueError('Source content hash does not match manifest')
            print('Sorting resolved rows on disk', flush=True)
            sorter.execute('CREATE INDEX chronology ON rows(utc,source,record,decision)')
            sorter.commit()
            canonical = stack.enter_context((staging / 'decisions.jsonl').open('wb'))
            files = {}
            for action in ('fold', 'call', 'raise'):
                for street in ('preflop', 'flop', 'turn', 'river'):
                    path = staging / action / f'{street}.jsonl'
                    path.parent.mkdir(exist_ok=True)
                    files[action, street] = stack.enter_context(path.open('wb'))
            previous, previous_hand, previous_time = None, None, None
            group_size, group_time = 0, None
            for utc, member, record, decision, payload in sorter.execute('SELECT * FROM rows ORDER BY utc,source,record,decision'):
                key = utc, member, record, decision
                if previous is not None and key <= previous:
                    raise ValueError('Output is not strictly ordered by timestamp/hand/decision key')
                previous = key
                hand_key = member, record
                if hand_key != previous_hand:
                    if utc == previous_time:
                        counts['tied_adjacent_hands'] += 1
                    if utc != group_time:
                        if group_size > 1:
                            counts['equal_timestamp_hand_groups'] += 1
                        group_time, group_size = utc, 0
                    group_size += 1
                    previous_hand, previous_time = hand_key, utc
                row = json.loads(payload)
                encoded = (payload + '\n').encode()
                canonical.write(encoded)
                files[row['label'], row['street']].write(encoded)
                resolved_digest.update(encoded)
                partitions[f"{row['label']}/{row['street']}"] += 1
                counts['written_resolved_rows'] += 1
                if counts['written_resolved_rows'] % 1000000 == 0:
                    print(f'Wrote {counts["written_resolved_rows"]:,} sorted rows', flush=True)
            if group_size > 1:
                counts['equal_timestamp_hand_groups'] += 1
            if counts['written_resolved_rows'] != counts['resolved_rows']:
                raise ValueError('Sorted row counts do not reconcile')
            for file in (canonical, unresolved, *files.values()):
                file.flush()
                os.fsync(file.fileno())
        report = {'status': 'complete', 'schema': 'utc-chronology-v1', 'source_dir': str(source),
                  'metadata_index': str(metadata), 'output_dir': str(destination),
                  'timezone_policy': TIMEZONE_POLICY, 'source_decisions_sha256': digest.hexdigest(),
                  'decisions_sha256': resolved_digest.hexdigest(), 'unresolved_sha256': unresolved_digest.hexdigest(),
                  'counts': dict(counts), 'timezone_hand_counts': dict(labels), 'partitions': dict(partitions),
                  'order': ['timestamp_utc', 'source_file', 'record_index', 'decision_index'],
                  'limitations': ['Unresolved timezone rows remain in a separate file and are not in the chronological corpus.',
                                  'Equal timestamps do not establish real order; do not learn across tied hands using the tie-breaker.',
                                  'Hand timestamps do not identify action/completion times or resolve overlapping hands.',
                                  'No player-history updates or train/validation/test split has been implemented.']}
        (staging / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
        for directory in (staging, *(staging / a for a in ('fold', 'call', 'raise'))):
            for path in directory.glob('*.json*'):
                with path.open('rb') as file:
                    os.fsync(file.fileno())
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        os.rename(staging, destination)
        fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return report
