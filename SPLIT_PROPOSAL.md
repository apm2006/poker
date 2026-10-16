# Proposed chronological evaluation splits

Status: dates approved by the user. Split creation uses these fixed UTC boundaries.

| Fold | Training dates (inclusive) | Validation dates (inclusive) | Training rows | Validation rows |
| --- | --- | --- | ---: | ---: |
| 1 | June 30–July 8, 2009 | July 9–11 | 1,878,401 | 550,609 |
| 2 | June 30–July 11 | July 12–14 | 2,429,010 | 507,687 |
| 3 | June 30–July 14 | July 15–17 | 2,936,697 | 591,150 |

Final test: July 18–26 inclusive, 698,054 rows from 308,187 hands. The interval ends at July 27 00:00:00 UTC (exclusive).

After model settings are selected, refit on all pre-test data: 3,527,847 rows. The final test is not used to choose model settings.

## Coverage checks

| Period | Hands | Rows | Fold % | Call % | Raise % | Smallest action/street count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| initial_training | 831,770 | 1,878,401 | 38.82 | 28.92 | 32.25 | 8,067 |
| validation_1 | 242,999 | 550,609 | 38.62 | 29.48 | 31.90 | 2,533 |
| validation_2 | 225,992 | 507,687 | 38.91 | 29.02 | 32.08 | 2,225 |
| validation_3 | 261,174 | 591,150 | 38.61 | 29.13 | 32.26 | 2,544 |
| final_test | 308,187 | 698,054 | 38.72 | 28.52 | 32.76 | 2,949 |

These are coverage-aware temporal blocks, not shuffled or mathematically stratified folds. Class frequencies are retained; future hands are never moved into earlier blocks to equalize labels.

## Site drift

| Period | PokerStars % | Full Tilt % | Absolute Poker % | PartyPoker % |
| --- | ---: | ---: | ---: | ---: |
| initial_training | 61.49 | 16.61 | 13.28 | 8.62 |
| validation_1 | 81.23 | 0.55 | 13.87 | 4.34 |
| validation_2 | 75.69 | 1.49 | 18.29 | 4.53 |
| validation_3 | 74.10 | 6.60 | 15.51 | 3.78 |
| final_test | 54.68 | 28.70 | 13.03 | 3.59 |

The late tail is sparse and has a different site mix. Starting the test on July 18 retains all four resolved sites and about 16.5% of the corpus, rather than making the test consist only of that tail. Evaluation should show per-site results as well as pooled results. No attempts have been made to rebalance sites or tune a model against final-test performance.

## Integrity and remaining decisions

- Full scan: 4,225,901 ordered resolved rows across 27 UTC dates; source hash matches the normalized manifest.
- Four rows fall on June 30 after converting original local July 1 timestamps. They stay in initial training.
- All decisions from a hand share a timestamp. UTC-midnight boundaries keep each hand and every equal-timestamp group in one temporal block.
- The 9,015 unresolved-timezone rows remain excluded from this chronology, preserved separately.
- Fit feature transforms on training data only. Raw IDs/date/source columns are provenance, not approved model inputs.
- No history-derived features have been computed. Tied and overlapping hands still need an approved conservative history-update policy; the storage tie-breaker cannot establish temporal precedence.
- No purge/embargo interval has been selected. Hand-start timestamps do not establish hand completion, so historical/personalization evaluation needs this resolved before implementation.
- The user approved these exact dates. No model settings have been selected.

The coverage command is `profile-dates`; detailed local reports are in `data/processed/date-profile.json` and `data/processed/split-proposal.json`.

## Split creation completed

`data/processed/temporal-splits-v1/` now contains all five blocks and their fold
manifest. Every block's row, hand, action, action/street, and site counts match
this coverage proposal. All 4,225,901 resolved rows are assigned exactly once.
The original normalized dataset is unchanged. No model fitting has occurred.
