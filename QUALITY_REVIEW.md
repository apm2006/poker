# Full-export quality review

Reviewed the completed export with processing version
`213aed8382d18293f1d58f84b89e90f811de1d4a0f062bf9c5be28ad6d751586`.
Source data, cached outcomes, and decision rows were not modified.

## Counts and exclusions

The export contains 4,234,916 decisions from 1,875,291 unique retained hands.
The canonical row count and all 12 action/street counts match the export summary.
Every retained hand has at least one decision row. SQLite enforces one selected
copy per site/hand ID.

| Rejection reason | Records |
| --- | ---: |
| Starting stacks not finite and positive | 1,089,441 |
| Blinds outside the approved positive 1:2 structure | 86,170 |
| Antes present | 3,739 |
| Replay did not reach completion | 35 |
| Missing hand ID | 20 |
| Total | 1,179,405 |

These categories account for every rejection and agree with approved filtering.
No inserted-decision rejection occurred in this export. This does not establish
that every source record is semantically complete beyond the replay checks.

## Warnings

- 1,875,291 warnings concern the unrecognized `time_zone_abbreviation` field:
  exactly one per retained hand. This metadata warning does not stop replay, but
  the original timezone is not preserved in decision rows or normalized.
- 1,144 warnings concern folding when checking was possible. Such folds are
  outside the positive-amount-to-call prediction task and do not become labels.
- These two messages account for all 1,876,435 retained-hand warnings.

## Feature checks

A full scan found no nonpositive amount-to-call rows, calls exceeding the actor's
stack, raise labels with `raise_legal = false`, invalid/nonfinite chip values,
unknown board cards, repeated board cards, or unexpected board lengths by street.
These are consistency checks, not independent verification of all source values.

**Issue in original export:** `effective_stack` means the minimum of the
two *remaining* stacks, ignoring chips already bet. This understates the actor's
additional amount at risk in 2,217,928 rows. There are 62,432 decisions facing an
opponent with no chips left; all currently have `effective_stack = 0` despite a
positive amount to call.

A synthetic $100/$100 hand demonstrates the issue: after one player shoves,
the other has $98 remaining and must call $98; the exported value is $0 while
PokerKit's `get_effective_stack(actor)` returns $98.

For these heads-up, facing-bet rows, the actor's additional amount at risk can be
derived as `min(actor_stack, opponent_stack + amount_to_call)`. This handles a
call capped by the actor's own stack. The associated stack/pot ratio must also
be corrected. The user approved this semantic definition and a separate derived correction.
The old value could alternatively be renamed as minimum chips behind, but must
not be used as the approved actor-risk feature. Corrected model inputs can be
derived from existing rows without replaying the archive; preserve the original
export and version any derived output.

The existing call/pot ratio measures bet pressure, not call equity's break-even
threshold. Pending feature work includes board texture and prior-action summaries;
player tendencies must be computed from earlier observations only.

## Coverage and chronology

| Site | Retained hands | Decisions |
| --- | ---: | ---: |
| PokerStars | 1,237,373 | 2,806,323 |
| Absolute Poker | 265,594 | 601,267 |
| Full Tilt Poker | 246,506 | 562,046 |
| PartyPoker | 120,649 | 256,265 |
| Ongame Network | 5,169 | 9,015 |

There are no retained iPoker hands; the approved stack filter removes its
nonfinite-stack records. PokerStars supplies about two-thirds of retained hands,
so evaluation should report site coverage rather than assume a uniform population.

Observed dates range from July 1 to July 26, 2009. Counts fall sharply after
July 20. The July 24–26 tail contains 1,305 hands and needs source/date review
before selecting a date cutoff. Do not assume the advertised July 1–23 window is
the actual timestamp range.

There are 25,804 site-scoped player identifiers with decisions, of which 7,314
have at least 100 decisions and 859 have at least 1,000. No row lacks player ID.
There are 7,936 rows without a table ID; they remain usable for prediction but
cannot support confident table-session classification from that field alone.

The export is in source-file order, not chronological order. Before deriving
player-history statistics or splitting, settle timezone handling and chronological
ordering. Sustained versus temporarily short-handed session tags are unfinished.

## Next decisions

1. Actor-risk effective-stack definition and derived correction approved; see
   `data/processed/effective-stack-v2/` for the corrected dataset after completion.
2. Review source timezones/date tails, then approve a chronological split.
3. Finalize feature encodings and build the first logistic-regression benchmark.

Aggregate machine-readable findings are saved beside the export as
`quality-review.json` and `quality-effective-stack.json` (ignored by Git).

## Correction completed

The derived `effective-stack-v2` dataset preserves all 4,234,916 rows and all
12 action/street counts. Both stack fields changed in 2,217,928 rows, including
62,432 all-in response rows whose actor-risk values are now positive. Future
replay snapshots use PokerKit's effective-stack calculation. The original
export and cache were not modified. Training should use the corrected copy.
Chronological splitting and remaining feature preparation are still pending.
