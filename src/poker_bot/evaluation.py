"""Dataset coverage checks for chronological evaluation; model metrics come later."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def profile_dates(source_dir, output):
    """Count UTC-date coverage without assigning rows to any training/test split."""
    source = Path(source_dir)
    manifest = json.loads((source / 'summary.json').read_text())
    if manifest.get('status') != 'complete':
        raise ValueError('Source dataset must be complete')
    days = defaultdict(lambda: {'rows': 0, 'hands': 0, 'actions': Counter(),
                                'street_actions': Counter(), 'site_rows': Counter(), 'site_hands': Counter()})
    digest = hashlib.sha256()
    previous_key = None
    previous_hand = None
    total = 0
    with (source / 'decisions.jsonl').open('rb') as stream:
        for raw in stream:
            digest.update(raw)
            row = json.loads(raw)
            stamp = row['timestamp_utc']
            if not stamp or not stamp.endswith('Z'):
                raise ValueError('Every row needs a resolved UTC timestamp')
            key = stamp, row['source_file'], row['record_index'], row['decision_index']
            if previous_key is not None and key <= previous_key:
                raise ValueError('Input is not in timestamp/hand/decision order')
            previous_key = key
            day = days[stamp[:10]]
            hand = row['source_file'], row['record_index']
            if hand != previous_hand:
                day['hands'] += 1
                day['site_hands'][row['site']] += 1
            previous_hand = hand
            day['rows'] += 1
            day['actions'][row['label']] += 1
            day['street_actions'][f"{row['street']}/{row['label']}"] += 1
            day['site_rows'][row['site']] += 1
            total += 1
            if total % 1000000 == 0:
                print(f'Profiled {total:,} rows', flush=True)
    if digest.hexdigest() != manifest['decisions_sha256']:
        raise ValueError('Source dataset hash does not match its manifest')
    expected = manifest['counts'].get('resolved_rows', manifest['counts'].get('rows'))
    if total != expected:
        raise ValueError('Source row count does not match its manifest')
    report = {'status': 'complete', 'source_dir': str(source.resolve()),
              'source_decisions_sha256': digest.hexdigest(), 'rows': total,
              'days': dict(sorted(days.items())),
              'scope': 'Coverage profile only; no split assignments or model fitting.'}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, indent=2) + '\n')
    tmp.replace(output)
    return report


def period_coverage(days, start, end):
    """Aggregate a half-open UTC date range for a proposed evaluation period."""
    result = {'start_inclusive': start, 'end_exclusive': end, 'rows': 0, 'hands': 0,
              'actions': Counter(), 'street_actions': Counter(), 'site_rows': Counter(), 'site_hands': Counter()}
    for day, values in days.items():
        if start <= day < end:
            result['rows'] += values['rows']
            result['hands'] += values['hands']
            for key in ('actions', 'street_actions', 'site_rows', 'site_hands'):
                result[key].update(values[key])
    return result


APPROVED_PERIODS = (
    ('initial_training', '2009-06-30', '2009-07-09'),
    ('validation_1', '2009-07-09', '2009-07-12'),
    ('validation_2', '2009-07-12', '2009-07-15'),
    ('validation_3', '2009-07-15', '2009-07-18'),
    ('final_test', '2009-07-18', '2009-07-27'),
)


def create_temporal_splits(source_dir, output_dir):
    """Write the approved disjoint UTC blocks and expanding-window manifest.

    Rows are copied byte-for-byte. This makes assignments only: no fitting,
    imputation, player-history updates, weighting, or resampling occurs.
    """
    from contextlib import ExitStack
    import os
    import tempfile

    source, destination = Path(source_dir).resolve(), Path(output_dir).resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and output directories must be separate')
    if destination.exists():
        raise FileExistsError('Choose a new output directory')
    manifest = json.loads((source / 'summary.json').read_text())
    if manifest.get('status') != 'complete':
        raise ValueError('Source dataset must be complete')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stats = {name: {'file': name + '.jsonl', 'start_inclusive': start, 'end_exclusive': end,
                    'rows': 0, 'hands': 0, 'actions': Counter(), 'street_actions': Counter(),
                    'site_rows': Counter()} for name, start, end in APPROVED_PERIODS}
    digest = hashlib.sha256()
    hashes = {name: hashlib.sha256() for name in stats}
    previous_key, previous_hand, previous_stamp, previous_block = None, None, None, None
    total = 0
    with tempfile.TemporaryDirectory(prefix='.temporal-splits-', dir=destination.parent) as work:
        work = Path(work)
        with ExitStack() as stack:
            files = {name: stack.enter_context((work / values['file']).open('wb')) for name, values in stats.items()}
            with (source / 'decisions.jsonl').open('rb') as stream:
                for raw in stream:
                    digest.update(raw)
                    row = json.loads(raw)
                    stamp = row['timestamp_utc']
                    if not stamp or not stamp.endswith('Z'):
                        raise ValueError('Expected a resolved UTC timestamp')
                    key = stamp, row['source_file'], row['record_index'], row['decision_index']
                    if previous_key is not None and key <= previous_key:
                        raise ValueError('Input rows are not chronologically ordered')
                    previous_key = key
                    block = next((name for name, start, end in APPROVED_PERIODS if start <= stamp[:10] < end), None)
                    if block is None:
                        raise ValueError('Row falls outside approved date ranges')
                    hand = row['source_file'], row['record_index']
                    if (hand == previous_hand or stamp == previous_stamp) and block != previous_block:
                        raise ValueError('A hand or equal-timestamp group crosses a split boundary')
                    if hand != previous_hand:
                        stats[block]['hands'] += 1
                    previous_hand, previous_stamp, previous_block = hand, stamp, block
                    files[block].write(raw)
                    hashes[block].update(raw)
                    values = stats[block]
                    values['rows'] += 1
                    values['actions'][row['label']] += 1
                    values['street_actions'][f"{row['street']}/{row['label']}"] += 1
                    values['site_rows'][row['site']] += 1
                    total += 1
                    if total % 1000000 == 0:
                        print(f'Assigned {total:,} rows', flush=True)
            expected = manifest['counts'].get('resolved_rows', manifest['counts'].get('rows'))
            if total != expected or digest.hexdigest() != manifest['decisions_sha256']:
                raise ValueError('Source count/hash does not match its manifest')
            if any(values['rows'] == 0 for values in stats.values()):
                raise ValueError('An approved period is empty')
            for file in files.values():
                file.flush()
                os.fsync(file.fileno())
        for name in stats:
            stats[name]['sha256'] = hashes[name].hexdigest()
        names = [name for name, _, _ in APPROVED_PERIODS]
        folds = [{'fold': i, 'train_files': [stats[n]['file'] for n in names[:i]],
                  'validation_file': stats[names[i]]['file'],
                  'training_rows': sum(stats[n]['rows'] for n in names[:i]),
                  'validation_rows': stats[names[i]]['rows']} for i in (1, 2, 3)]
        report = {'status': 'complete', 'schema': 'approved-temporal-splits-v1',
                  'source_dir': str(source), 'output_dir': str(destination),
                  'source_decisions_sha256': digest.hexdigest(), 'rows': total,
                  'blocks': stats, 'folds': folds,
                  'final_refit_files': [stats[n]['file'] for n in names[:-1]],
                  'final_test_file': stats['final_test']['file'],
                  'limitations': ['These are chronological blocks with coverage checks, not shuffled stratified folds.',
                                  'No model or preprocessing transform has been fitted.',
                                  'No purge/embargo or overlapping-hand history-update rule has been selected.',
                                  'Keep the final test out of feature/hyperparameter selection.']}
        (work / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
        with (work / 'summary.json').open('rb') as file:
            os.fsync(file.fileno())
        fd = os.open(work, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.rename(work, destination)
        fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return report
