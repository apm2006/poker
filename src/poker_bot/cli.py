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
    args = parser.parse_args()
    if args.command == 'audit':
        report = audit_zip(args.archive, args.output)
        print(json.dumps(report, indent=2))
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
