"""PokerKit compatibility probe; not yet the gameplay engine adapter."""

from collections import Counter, defaultdict
from importlib.metadata import version
import json
import math
from pathlib import Path
import warnings
import zipfile

from .data import fields, literal, records


def compatibility_sample(archive, per_group=5):
    """Take a deterministic smoke-test sample per source/stake folder.

This is not a random or deduplicated training export. Limit scanning to three
files per group so sources without eligible records do not cause a full audit.
    """
    groups = defaultdict(list)
    with zipfile.ZipFile(archive) as source:
        for name in sorted(source.namelist()):
            if '/handhq/' in name and name.endswith('.phhs'):
                groups[name.split('/handhq/', 1)[1].split('/')[0]].append(name)
        for group, names in groups.items():
            selected = 0
            for name in names[:3]:
                with source.open(name) as stream:
                    for raw in records(stream):
                        values = fields(raw)
                        try:
                            stacks = literal(values, 'starting_stacks')
                            if (literal(values, 'variant') != 'NT' or len(stacks) != 2
                                    or not all(math.isfinite(x) and x > 0 for x in stacks)):
                                continue
                            blinds = literal(values, 'blinds_or_straddles')
                            if (any(literal(values, 'antes')) or len(blinds) != 2
                                    or min(blinds) <= 0 or max(blinds) != 2 * min(blinds)):
                                continue
                            if any(key not in values for key in ('players', 'seats', 'winnings', 'table', 'year', 'month', 'day', 'time', 'actions', 'venue', 'hand')):
                                continue
                        except (ValueError, SyntaxError, KeyError, TypeError):
                            continue
                        yield group, name, raw
                        selected += 1
                        if selected >= per_group:
                            break
                if selected >= per_group:
                    break


def check_compatibility(archive, output, per_group=5):
    if per_group < 1:
        raise ValueError('per_group must be positive')
    sample = list(compatibility_sample(archive, per_group))
    counts = Counter()
    warning_counts = Counter()
    groups = Counter(group for group, _, _ in sample)
    report = {'sample_counts_by_group': dict(groups), 'sample_size': len(sample),
              'sampling': 'First eligible records from up to three sorted files per source/stake group; smoke test only.',
              'limitations': ['Not a full archive validation, identity check, or training export.',
                              'Successful replay does not verify source winnings, rake, or absence of hidden-information leakage.']}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Export only the local smoke-test sample, preserving original record fields.
    sample_path = output.with_suffix('.phhs')
    with sample_path.open('wb') as stream:
        for index, (_, _, raw) in enumerate(sample, 1):
            stream.write(f'[{index}]\n'.encode() + raw + b'\n')
    report['sample_path'] = str(sample_path)
    try:
        from pokerkit import HandHistory
    except ModuleNotFoundError as exc:
        if exc.name != 'pokerkit':
            raise
        report['status'] = 'blocked_missing_pokerkit'
        report['next_step'] = 'Install pokerkit==0.7.6 in the project virtual environment and rerun.'
    else:
        report['pokerkit_version'] = version('pokerkit')
        failures = []
        for group, name, raw in sample:
            try:
                with warnings.catch_warnings(record=True) as observed:
                    warnings.simplefilter('always')
                    history = HandHistory.loads(raw.decode())
                    last = None
                    for state in history:
                        last = state
                        # Read required properties immediately: PokerKit mutates states.
                        if state.actor_index is not None:
                            assert len(state.stacks) == 2
                            assert state.total_pot_amount >= 0
                            assert state.checking_or_calling_amount is not None
                            counts['betting_states_observed'] += 1
                    counts['replay_success'] += 1
                    counts['completed' if last is not None and not last.status else 'incomplete'] += 1
                    counts['warnings'] += len(observed)
                    for warning in observed:
                        warning_counts[f'{warning.category.__name__}: {warning.message}'] += 1
            except Exception as exc:
                counts['replay_failed'] += 1
                failures.append({'group': group, 'file': name,
                                 'hand': fields(raw).get('hand'),
                                 'error': f'{type(exc).__name__}: {exc}'})
        report.update(status='probe_finished', counts=dict(counts),
                      warning_counts=dict(warning_counts), failures=failures)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report
