"""Versioned, disk-backed PHH export with whole-file checkpoints."""

from collections import Counter
from contextlib import ExitStack
import fcntl
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sqlite3
import zipfile

from .data import fields, literal, records, replay_record


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def processing_version():
    """Invalidate on validator, features, cache implementation, or PokerKit changes."""
    base = Path(__file__).parent
    config = {'schema': 1, 'pokerkit': version('pokerkit'),
              'code': {name: file_hash(base / name) for name in ('data.py', 'features.py', 'cache.py')}}
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(), config


def durable_replace(temporary, final):
    with Path(temporary).open('rb') as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, final)
    descriptor = os.open(str(Path(final).parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def record_result(raw):
    """Cache deterministic validation outcomes; unexpected software errors abort."""
    try:
        values = fields(raw)
        site, hand = literal(values, 'venue'), str(literal(values, 'hand'))
        rows, counts, warnings = replay_record(raw)
        return {'accepted': True, 'site': site, 'hand': hand, 'rows': rows,
                'counts': counts, 'warnings': warnings}
    except (ValueError, TypeError, KeyError, SyntaxError, UnicodeError) as exc:
        return {'accepted': False, 'reason': f'{type(exc).__name__}: {exc}'}


def export_cached(archive, output_dir, max_files=None):
    """Stream a sorted ZIP prefix, reusing completed chunks on subsequent calls.

Only a single hand's rows are held in memory. A per-file transaction contains
record outcomes, chosen hand identities, and completion metadata. Chunk writes
precede commit; abandoned chunks from rolled-back transactions are overwritten.
    """
    if max_files is not None and max_files < 1:
        raise ValueError('max_files must be positive')
    archive = Path(archive).resolve()
    processing, config = processing_version()
    source_hash = file_hash(archive)
    root = Path(output_dir) / processing / source_hash
    root.mkdir(parents=True, exist_ok=True)
    run = Counter()
    with ExitStack() as stack:
        lock = stack.enter_context((root / 'export.lock').open('a'))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('An export is already using this cache') from None
        marker = root / 'summary.json'
        marker_tmp = marker.with_suffix('.tmp')
        marker_tmp.write_text(json.dumps({'status': 'building', 'output_dir': str(root.resolve())}) + '\n')
        durable_replace(marker_tmp, marker)
        db = sqlite3.connect(root / 'cache.sqlite')
        stack.callback(db.close)
        db.executescript('''
            CREATE TABLE IF NOT EXISTS outcomes (digest TEXT PRIMARY KEY, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chosen (site TEXT, hand TEXT, digest TEXT, PRIMARY KEY(site,hand));
            CREATE TABLE IF NOT EXISTS completed (name TEXT PRIMARY KEY, chunk TEXT, chunk_hash TEXT,
                rejected TEXT, rejected_hash TEXT, stats TEXT);
        ''')
        source = stack.enter_context(zipfile.ZipFile(archive))
        names = sorted(n for n in source.namelist() if '/handhq/' in n and n.endswith('.phhs'))
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP member names are ambiguous')
        selected = names[:max_files] if max_files else names
        chunks = root / 'chunks'
        chunks.mkdir(exist_ok=True)
        for file_index, name in enumerate(selected, 1):
            previous = db.execute('SELECT chunk,chunk_hash,rejected,rejected_hash FROM completed WHERE name=?', (name,)).fetchone()
            if previous:
                for path, digest in ((previous[0], previous[1]), (previous[2], previous[3])):
                    if not (root / path).exists() or file_hash(root / path) != digest:
                        raise RuntimeError('Completed cache chunk is missing or damaged; use a new output directory to rebuild')
                run['files_reused'] += 1
                continue
            key = hashlib.sha256(name.encode()).hexdigest()
            chunk, rejected = chunks / f'{key}.jsonl', chunks / f'{key}.rejected.jsonl'
            tmp, rejected_tmp = chunk.with_suffix('.tmp'), rejected.with_suffix('.tmp')
            stats = Counter()
            db.execute('BEGIN IMMEDIATE')
            try:
                with source.open(name) as stream, tmp.open('w') as output, rejected_tmp.open('w') as errors:
                    for record_index, raw in enumerate(records(stream), 1):
                        stats['records'] += 1
                        # Skip irrelevant variants/player counts without creating millions of replay-cache entries.
                        try:
                            values = fields(raw)
                            if literal(values, 'variant') != 'NT' or len(literal(values, 'starting_stacks')) != 2:
                                stats['outside_heads_up_scope'] += 1
                                continue
                        except (ValueError, TypeError, KeyError, SyntaxError, UnicodeError):
                            pass  # The validator records the malformed-record rejection below.
                        digest = hashlib.sha256(raw).hexdigest()
                        cached = db.execute('SELECT result FROM outcomes WHERE digest=?', (digest,)).fetchone()
                        if cached:
                            result = json.loads(cached[0])
                            run['record_cache_hits'] += 1
                        else:
                            result = record_result(raw)
                            db.execute('INSERT INTO outcomes VALUES (?,?)', (digest, json.dumps(result, allow_nan=False)))
                            run['records_validated'] += 1
                        if not result['accepted']:
                            stats['hands_rejected'] += 1
                            errors.write(json.dumps({'source_file': name, 'record_index': record_index,
                                                     'record_hash': digest, 'reason': result['reason']}) + '\n')
                            continue
                        old = db.execute('SELECT digest FROM chosen WHERE site=? AND hand=?', (result['site'], result['hand'])).fetchone()
                        if old:
                            stats['exact_duplicates_skipped' if old[0] == digest else 'conflicting_copies_skipped'] += 1
                            continue
                        db.execute('INSERT INTO chosen VALUES (?,?,?)', (result['site'], result['hand'], digest))
                        stats['hands_retained'] += 1
                        stats['warnings'] += sum(result['warnings'].values())
                        for row in result['rows']:
                            row.update(source_file=name, record_index=record_index, record_hash=digest)
                            output.write(json.dumps(row, allow_nan=False) + '\n')
                            stats['rows'] += 1
                            stats[f"{row['label']}/{row['street']}"] += 1
                durable_replace(tmp, chunk)
                durable_replace(rejected_tmp, rejected)
                db.execute('INSERT INTO completed VALUES (?,?,?,?,?,?)',
                           (name, str(chunk.relative_to(root)), file_hash(chunk),
                            str(rejected.relative_to(root)), file_hash(rejected), json.dumps(dict(stats))))
                db.commit()
            except BaseException:
                db.rollback()
                raise
            run['files_processed'] += 1
            print(f'Exported file {file_index}/{len(selected)}: {stats["hands_retained"]} hands, {stats["rows"]} rows', flush=True)
        # Rebuild views from committed chunks, rather than appending to previous output.
        totals = Counter()
        with ExitStack() as outputs:
            destinations = {'decisions.jsonl': None, 'rejections.jsonl': None}
            destinations.update({f'{action}/{street}.jsonl': None for action in ('fold', 'call', 'raise')
                                 for street in ('preflop', 'flop', 'turn', 'river')})
            for path in destinations:
                final = root / path
                final.parent.mkdir(parents=True, exist_ok=True)
                destinations[path] = outputs.enter_context(final.with_suffix('.tmp').open('w'))
            for name in selected:
                chunk, rejected, stats = db.execute('SELECT chunk,rejected,stats FROM completed WHERE name=?', (name,)).fetchone()
                totals.update(json.loads(stats))
                with (root / chunk).open() as stream:
                    for line in stream:
                        row = json.loads(line)
                        destinations['decisions.jsonl'].write(line)
                        destinations[f"{row['label']}/{row['street']}.jsonl"].write(line)
                with (root / rejected).open() as stream:
                    for line in stream:
                        destinations['rejections.jsonl'].write(line)
        for path in destinations:
            final = root / path
            durable_replace(final.with_suffix('.tmp'), final)
        report = {'status': 'complete', 'processing_version': processing, 'configuration': config, 'archive_sha256': source_hash,
                  'output_dir': str(root.resolve()), 'archive_files': len(names), 'selected_files': len(selected),
                  'full_archive': len(selected) == len(names), 'counts': dict(totals), 'this_run': dict(run),
                  'limitations': ['Not session-classified or timezone-normalized; features are still preliminary.',
                                  'Completed source files are resume checkpoints; an interrupted current file is reprocessed.',
                                  'Use summary.json as the completion marker; final views are rebuilt after interruptions.']}
        summary = root / 'summary.json'
        temporary = summary.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        durable_replace(temporary, summary)
        return report
