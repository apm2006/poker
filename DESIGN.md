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

