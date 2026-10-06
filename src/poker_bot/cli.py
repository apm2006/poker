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
    args = parser.parse_args()
    if args.command == 'audit':
        report = audit_zip(args.archive, args.output)
        print(json.dumps(report, indent=2))
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
