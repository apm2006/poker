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
    args = parser.parse_args()
    if args.command == 'audit':
        report = audit_zip(args.archive, args.output)
        print(json.dumps(report, indent=2))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
