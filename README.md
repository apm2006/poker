# Adaptive poker bot

Temporary skeleton for a heads-up opponent that learns player tendencies using
classical ML. A preliminary read-only dataset audit is implemented; training and gameplay are
not implemented yet.

## Run the skeleton

Requires Python 3.11 or newer. No third-party runtime dependencies are needed.

```sh
PYTHONPATH=src python3 -m poker_bot.cli
PYTHONPATH=src python3 -m poker_bot.cli --help
PYTHONPATH=src python3 -m poker_bot.cli audit /path/to/phh-dataset-main.zip
```

## Layout

- `src/poker_bot/data.py`: PHH ingestion, validation, and initial heads-up filtering.
- `src/poker_bot/game.py`: game state and legal actions.
- `src/poker_bot/features.py`: observable decision inputs.
- `src/poker_bot/models.py`: classical ML implementations, once approved.
- `src/poker_bot/opponent.py`: player history and adaptation.
- `src/poker_bot/bot.py`: baseline and adaptive action selection.
- `src/poker_bot/evaluation.py`: prediction and poker performance evaluation.
- `src/poker_bot/cli.py`: terminal entry point.
- `data/raw/`: source data; original ZIP currently remains in Downloads.
- `data/processed/`: filtered and generated training data.
- `tests/`: future correctness checks as behavior is implemented.
- `DESIGN.md`: agreed direction and decisions awaiting review.

Audit output defaults to `data/processed/audit.json`. Dataset contents and generated
reports are excluded from version control. Audit candidates still need legal
replay, completion, conflict, and session checks before training.

Run audit correctness checks with:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

Starting stacks must now be finite for a hand to pass the audit's candidate filter.
The existing full audit was generated before this rule; its counts are historical.
Rerun the audit command to generate updated counts with the finite-stack filter.
