"""Terminal entry points for dataset inspection."""

import argparse
import json
from .data import audit_zip


def main() -> None:
    parser = argparse.ArgumentParser(description='Adaptive heads-up poker bot.')
    commands = parser.add_subparsers(dest='command')
    audit = commands.add_parser('audit', help='Audit human records in a PHH ZIP without extraction')
    audit.add_argument('archive')
    audit.add_argument('--output', default='data/processed/audit.json')
    probe = commands.add_parser('check-pokerkit', help='Replay a small PHH compatibility sample')
    probe.add_argument('archive')
    probe.add_argument('--output', default='data/processed/pokerkit-check.json')
    probe.add_argument('--per-group', type=int, default=5)
    extract = commands.add_parser('extract-decisions', help='Extract pre-action inspection rows from a PHH sample')
    extract.add_argument('sample')
    extract.add_argument('--output-dir', default='data/processed/sample-decisions')
    cached = commands.add_parser('export-cached', help='Resume a versioned streaming export from a PHH ZIP')
    cached.add_argument('archive')
    cached.add_argument('--output-dir', default='data/processed/cached-export')
    cached.add_argument('--max-files', type=int)
    correction = commands.add_parser('correct-effective-stacks', help='Derive corrected effective-stack features from existing decision rows')
    correction.add_argument('source_dir')
    correction.add_argument('--output-dir', required=True)
    chronology = commands.add_parser('normalize-timestamps', help='Create a UTC-sorted dataset and separate unresolved timezone rows')
    chronology.add_argument('source_dir')
    chronology.add_argument('--metadata-index', required=True)
    chronology.add_argument('--output-dir', required=True)
    profile = commands.add_parser('profile-dates', help='Count chronological class/street/site coverage by UTC date')
    profile.add_argument('source_dir')
    profile.add_argument('--output', default='data/processed/date-profile.json')
    splits = commands.add_parser('create-splits', help='Write approved temporal blocks and expanding-window fold manifest')
    splits.add_argument('source_dir')
    splits.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    if args.command == 'audit':
        report = audit_zip(args.archive, args.output)
        print(json.dumps(report, indent=2))
    elif args.command == 'create-splits':
        from .evaluation import create_temporal_splits
        print(json.dumps(create_temporal_splits(args.source_dir, args.output_dir), indent=2))
    elif args.command == 'profile-dates':
        from .evaluation import profile_dates
        report = profile_dates(args.source_dir, args.output)
        print(json.dumps({'rows': report['rows'], 'days': len(report['days']), 'output': args.output}, indent=2))
    elif args.command == 'normalize-timestamps':
        from .chronology import normalize_and_sort
        print(json.dumps(normalize_and_sort(args.source_dir, args.metadata_index, args.output_dir), indent=2))
    elif args.command == 'correct-effective-stacks':
        from .data import correct_effective_stacks
        print(json.dumps(correct_effective_stacks(args.source_dir, args.output_dir), indent=2))
    elif args.command == 'export-cached':
        from .cache import export_cached
        print(json.dumps(export_cached(args.archive, args.output_dir, args.max_files), indent=2))
    elif args.command == 'extract-decisions':
        from .data import extract_decisions
        report = extract_decisions(args.sample, args.output_dir)
        print(json.dumps(report, indent=2))
        if report['failures'] or not report['rows']:
            parser.exit(1)
    elif args.command == 'check-pokerkit':
        from .game import check_compatibility
        report = check_compatibility(args.archive, args.output, args.per_group)
        print(json.dumps(report, indent=2))
        if report['status'] != 'probe_finished' or report.get('counts', {}).get('replay_failed') or not report['sample_size']:
            parser.exit(1)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
