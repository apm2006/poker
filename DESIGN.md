# Project design

## Approved direction

- Build a local poker opponent that adapts to the user's play using classical ML.
- Use Python 3.11+, a package under `src/poker_bot`, and a terminal entry point first.
- Start with individual modules; introduce more code folders only when justified.
- Separate dataset preparation, game state, features, models, opponent tracking,
  action selection, and evaluation.
- Train the main opponent model on hands dealt to exactly two players. Multiplayer
  hands that later become heads-up do not qualify.
- Keep hidden opponent cards and future information out of decision features.
- Keep the original dataset ZIP unchanged.
- Keep source records in `data/raw/` and generated datasets in `data/processed/`.
  Their contents are ignored by version control.

## Approved model direction

- Multinomial logistic regression supplies population-level action probabilities.
- Bayesian frequency estimates personalize predictions from observed player actions:
  Beta-Binomial for binary responses and Dirichlet-Categorical for multiple actions.
- Start personal estimates with population-informed priors; let observed evidence
  increasingly influence estimates. Prior strength and the combination method are
  not selected yet.
- Predictions inform poker action evaluation; these models alone are not a playing
  strategy.
- K-means and gradient-boosted trees are not part of the initial approved approach.

## Decisions requiring user review before implementation

- Poker variant, stacks, blinds, antes, and allowed bet sizes. Heads-up no-limit
  Hold'em is a proposal; detailed gameplay rules are not yet selected.
- Poker engine, hand evaluator, and equity estimation method.
- Baseline playing strategy and action evaluation method.
- Model interfaces, ML dependencies, regularization, and training configuration.
- Bayesian context grouping, prior strength, prediction combination, and weighting
  of recent play.
- Detailed legal-replay validation, conflict resolution, player identity verification,
  and sustained heads-up session classification.
- Feature schema, train/test split, evaluation metrics, and benchmark opponents.
- Gameplay interface beyond the initial CLI.

This skeleton defines responsibilities only. It does not implement training,
gameplay, or a claim of a competent baseline. New design choices must be reviewed
with the user before implementation.

## Approved data and first prediction task

- Human no-limit Hold'em, exactly two initial players, standard small/big blinds,
  no antes or straddles for version one.
- Exclude malformed/incomplete records from training and report exclusion reasons.
- Deduplicate using source, hand ID, and contents; flag conflicting copies.
- Retain unknown hole cards. Preserve site, player ID, table, and timestamps;
  treat player IDs as site-specific until verified.
- Retain temporarily short-handed two-player hands and distinguish sustained
  heads-up sessions for comparison before any additional exclusion decision.
- First prediction task: fold/call/raise when facing a bet.
- Initial feature direction: street, position, amount to call relative to pot,
  effective stack relative to pot, prior action summaries, board texture, and
  player tendencies calculated from earlier hands only.
- Evaluate with earlier training hands and later test hands, keeping each hand
  in one split. Measure log loss and calibration.

## Audit implementation status

The ZIP audit streams HandHQ files without extraction and writes aggregate counts
under `data/processed/`. It performs preliminary structural filtering and identity
checks only. Candidates are not training-ready: full poker replay, completion
checks, conflict resolution, and session/identity verification remain outstanding.

## Full archive audit findings

- Human records scanned: 21,606,087 across 21,782 files.
- Exactly two initial players: 3,054,696 no-limit Hold'em hands.
- Unique preliminary structural candidates: 2,752,001 (including the first copy
  of 104 conflicting identities, which still need resolution).
- Two-player hands with nonfinite stacks: 1,089,441; these cannot directly supply
  the planned effective-stack feature.
- 212,582 records were flagged by parsing/structure checks, including absent
  winnings metadata. Flags alone do not establish corruption or incompleteness.
- 3,739 two-player hands had antes; 86,269 failed the preliminary blind check.
- One exact duplicate candidate and 104 conflicting identity copies were found.
- Most candidates contain unknown hole cards, as expected.

The counts above describe the audit before the finite-stack exclusion rule.
They must not be presented as updated eligible training counts.

## Approved finite-stack filter

- Require both starting stacks to be finite numbers. Exclude a hand if either
  stack is infinite or NaN; do not impute a replacement.
- Keep the source archive unchanged. Count excluded hands separately in audits.
- The existing positive-stack validation also remains in place.
- Handling missing metadata still requires review before training preparation.


## Approved PokerKit compatibility experiment

- Use PokerKit to check compatibility with PHH records and the project's Python
  setup, before implementing gameplay or training-row extraction.
- Probe dependency pinned to 0.7.6 for reproducibility; future version changes and
  permanent gameplay integration remain open.
- Keep full dataset exports local and ignored; only code and documentation belong
  in Git. The local smoke-test sample is not a training export.
- First sample: 100 finite-stack heads-up records across 20 source/stake groups.
- PokerKit was installed by the user and the sample replay was verified locally:
  100 successful, completed hands; 266 betting states; no replay failures.
- Warning breakdown: 100 unexpected `time_zone_abbreviation` metadata fields and
  two folds when the acting player had already matched the outstanding bet.
- No metadata rewriting, warning suppression, or exclusion of warning-bearing
  hands has been implemented. Training handling of these warnings needs review.
- These results establish small-sample compatibility, not full-archive validation.

## Approved sample decision extraction

- Extract recorded fold/call/raise decisions only when the player faces a positive
  amount to call. Pre-action features are copied before advancing replay.
- Produce one canonical local file and action/street inspection copies following
  the user's suggested breakdown. No separate per-action/street models selected.
- Keep row identities and timestamps for provenance and hand-level splitting;
  they are not approved model features.
- Initial sample: 100 hands, 191 decisions (96 fold, 34 call, 61 raise), no hand
  failures or inferred betting actions. Seventy-five recorded actions outside
  the facing-bet task were skipped.
- Tests verify known pre-action pot/stack amounts, action/street labeling,
  partition consistency, and independence from hidden hole cards.
- Player-history features, board-texture encodings, full-corpus export, and
  treatment of repaired histories remain outstanding.

## Approved duplicate and missing-data rules

- Keep one validated copy per site and hand ID. A rejected first copy does not
  reserve the identity; the first subsequent valid copy may be retained. Once a
  valid copy is kept, skip further exact or conflicting copies and count them.
- Reject the entire hand when PokerKit inserts an unrecorded betting decision
  (check/call, fold, or raise). Automatic bookkeeping is allowed.
- Reject missing/nonfinite essential chip values, unknown decision-time board
  cards, inconsistent replay, and histories that do not reach completion.
- Unknown private hole cards are allowed; they are not decision inputs.
- Missing optional table, seats, or winnings metadata alone does not reject a hand.
  Require a valid date/time for chronological splitting and site/hand for identity.
- No average substitutes for missing actions, stacks, bets, or board cards.
  Population estimates for optional player tendency statistics remain part of the
  approved Bayesian approach; no such imputation is implemented yet.
- These rules are implemented in the sample decision exporter. The earlier audit
  is a conservative structural diagnostic, not the final training eligibility rule.
- Rechecked the 100-hand sample: 100 retained, 191 decisions, no inserted betting
  decisions. Tests cover deduplication, invalid-first/valid-second copies,
  whole-hand rejection on inserted checks, optional metadata, and unknown boards.
- Full archive execution remains outstanding. The original sample command stays
  in-memory; the cached exporter below implements disk-backed streaming.

## Approved persistent cache and streaming export

- SQLite stores per-record hashes/outcomes, validated decision rows, duplicate
  identities, and completed ZIP-member checkpoints. Per-member chunks hold output.
- Namespaces include the archive SHA-256, processing-code hashes, schema version,
  and PokerKit version, preventing reuse across incompatible inputs or logic.
- Preserve the same approved validation rules through a shared per-hand replay
  function used by the sample and cached exporters.
- Commit file completion only after chunk writes are durable. Roll back current
  file identities/outcomes on failure; completed files survive interruptions.
- Rebuild final combined/action/street views from committed chunks. Report
  `building` until all views are written, then mark the selected scope complete.
- Bounded runs select a sorted source-file prefix. Omit `--max-files` for a full
  run; no full archive run has been performed yet.
- Cache eviction and automatic recovery from corrupted chunks are not implemented.
  Corruption is detected and reported; a new output directory permits rebuilding.
- Validated on 3 files: 2,998 records; 1,030 retained hands; 86 rejected;
  2,217 decisions, including 45 river calls and 3 river raises. Repeat run reused
  all 3 files without validation. Twenty tests cover validation and caching,
  including interrupted chunk commits and interrupted final-output assembly.
