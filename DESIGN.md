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

## Decisions requiring user review before implementation

- Poker variant, stacks, blinds, antes, and allowed bet sizes. Heads-up no-limit
  Hold'em is a proposal; detailed gameplay rules are not yet selected.
- Poker engine, hand evaluator, and equity estimation method.
- Baseline playing strategy and action evaluation method.
- Classical ML algorithms, model interfaces, and dependencies.
- Personalization method and weighting of recent play.
- Dataset validation, deduplication, player identity handling, and session filtering.
- Feature schema, train/test split, evaluation metrics, and benchmark opponents.
- Gameplay interface beyond the initial CLI.

This skeleton defines responsibilities only. It does not implement training,
gameplay, or a claim of a competent baseline. New design choices must be reviewed
with the user before implementation.
