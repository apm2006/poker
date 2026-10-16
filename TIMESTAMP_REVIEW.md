# Timestamp metadata and ordering review

## Scope and result

Read-only check of all 4,234,916 corrected decision rows and their 1,875,291
retained source hands across 9,429 ZIP members. The source archive, cached export,
and corrected decision files were not changed. The raw metadata index and audit
report are under ignored `data/processed/timestamp-review/`.

- All retained source hand IDs, site names, dates, and time strings match the
  decision export. No source metadata mismatch was found.
- All retained date/time values parse. No timestamp contains an explicit UTC offset.
- A hand's decision rows have consistent timestamps and increasing decision indices.
- Each individual source file's retained hands are nondecreasing by recorded
  local timestamp.
- **The combined export is not chronological:** 864 backward timestamp transitions
  occur between adjacent retained hands, all at source-file boundaries. There are
  860 backwards transitions when tracking the previous hand within each site.
  These comparisons use recorded local times, not normalized UTC times.
- Example: the export moves from July 5 at 19:43:30 to July 1 at 02:21:04 when
  beginning another Absolute Poker source file.

The current order is source-file order and must not drive historical player
statistics or temporal train/test splitting.

## Original timezone fields

Every retained hand has `time_zone_abbreviation` in the source. None uses the
recognized PHH `time_zone` field. The decision export omitted these abbreviations,
so it must be joined back to source metadata before absolute-time sorting.

| Site | Raw timezone label | Retained hands |
| --- | --- | ---: |
| Absolute Poker | ET | 265,594 |
| Full Tilt Poker | ET | 246,506 |
| PokerStars | ET | 1,237,373 |
| PartyPoker | EDT | 70,005 |
| PartyPoker | CEST | 49,950 |
| PartyPoker | ICT | 694 |
| Ongame Network | GMT-0910 | 5,169 |

PartyPoker's records use multiple labels, so a single offset per site would be
incorrect. `GMT-0910` is unusual: this review does not establish its intended
meaning or assume it is a reliable numeric UTC offset. Preserve that value until
an interpretation is supported and approved.

## Date tail

All July 24–26 values also occur in the original PHH records. Their presence was
not introduced by our exporter. This establishes source agreement, not that the
source clock was accurate.

| Date | Site | Raw timezone | Hands |
| --- | --- | --- | ---: |
| July 24 | Ongame Network | GMT-0910 | 27 |
| July 24 | PartyPoker | CEST | 466 |
| July 24 | PartyPoker | EDT | 295 |
| July 25 | PartyPoker | CEST | 314 |
| July 25 | PartyPoker | EDT | 88 |
| July 26 | PartyPoker | CEST | 102 |
| July 26 | PartyPoker | ICT | 13 |

Do not discard the tail solely because the archive folder names advertise a
July 1–23 collection period.

## Equal-time hands

196,301 adjacent pairs of distinct retained hands share the same recorded date
and time. This is an adjacency count, not the number of unique tied groups across
the corpus. The timestamps do not establish an order within those ties, nor do
they provide exact action times or hand-completion times.

A deterministic sort key can preserve stable row order, but it must not invent
behavioral evidence: do not update player-history statistics from one same-time
hand and expose them to another merely because its ID sorts later. Overlapping
hands and unknown completion times also need a conservative history-update rule.

## Approved normalization approach

1. Agree on explicit timezone interpretations for ET, EDT, CEST, and ICT.
2. Keep unresolved Ongame timestamps separate pending clarification, without
   altering the original records or guessing an offset.
3. Create a separate UTC-normalized, externally sorted derived dataset, preserving
   raw timestamps/labels, source identity, and within-hand decision order.
4. Check that normalized output is nondecreasing and counts reconcile. Settle
   tied/overlapping-hand history updates before calculating player tendencies.
5. Then select and approve chronological training/validation/test boundaries.

The SQLite metadata index is keyed by source file and record index so metadata
can be joined to the corrected rows without replaying poker hands.

The user approved this approach. `normalize-timestamps` implements the explicit
ET/EDT/CEST/ICT policy documented in `DESIGN.md`, keeping GMT-0910 separate.
No split dates or historical-feature update rules have been approved yet.

## Normalized copy completed

`data/processed/chronological-v1/` contains 4,225,901 UTC-ordered decision rows
from 1,870,122 hands. The separate `unresolved-timezones.jsonl` preserves all
9,015 rows from 5,169 Ongame hands. Their sum matches all 4,234,916 source rows.
The source content hash matches the effective-stack-v2 manifest. All resolved
rows were checked for timestamp/hand/decision ordering during publication.

The resolved corpus has 502,399 equal-timestamp groups containing multiple hands;
756,231 adjacent hand transitions are tied after sorting. Secondary keys do not
resolve real temporal order. This is why historical-feature update rules remain
an explicit decision before personalization training.
