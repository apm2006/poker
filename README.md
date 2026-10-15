# PokerBot

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

## PokerKit compatibility check

PokerKit 0.7.6 is pinned for the initial compatibility experiment. Install and run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install pokerkit==0.7.6
PYTHONPATH=src .venv/bin/python -m poker_bot.cli check-pokerkit /Users/apmanasani/Downloads/phh-dataset-main.zip
```

The command exports a small local PHH sample and writes a report in
`data/processed/pokerkit-check.json`. It tests loading, replay, required game-state
properties, and terminal status. It records replay errors and warning counts.
This deterministic sample is a smoke test, not a full compatibility guarantee or
training dataset. Source winnings and rake are not yet validated.

The compatibility sample contains 100 hands across 20 source/stake groups.
With PokerKit 0.7.6, all 100 replayed and reached terminal states, exposing 266
betting states. Warnings comprised 100 unrecognized `time_zone_abbreviation`
metadata fields and two folds with no outstanding amount to match. Warning
messages and counts are now included in the report. Full-dataset compatibility
and a warning-handling policy remain unverified/unselected.

## Sample decision extraction

```sh
PYTHONPATH=src .venv/bin/python -m poker_bot.cli extract-decisions data/processed/pokerkit-check.phhs
```

Outputs under ignored `data/processed/sample-decisions/`:

- `decisions.jsonl`: canonical pre-action rows with fold/call/raise labels.
- `fold/`, `call/`, `raise/`: inspection copies in preflop/flop/turn/river files.
- `summary.json`: counts, warnings, inferred betting actions, and failures.

Each row contains observable pre-decision pot, amount to call, remaining stacks,
minimum remaining stack, position, board, prior recorded betting actions, and
raise legality. The minimum remaining stack is calculated before the response;
no stack-depth or pot-odds formula beyond these reported ratios is yet selected.
Identifiers and timestamps are provenance, not model inputs. Hole cards and
outcomes are not exported. Player-history features and board-texture encodings
are still pending. Do not concatenate partition files with the canonical file:
they contain the same rows. Splits must keep all decisions from a hand together.

The 100-hand sample yielded 191 rows: 96 folds, 34 calls, and 61 raises, with no
inferred betting actions and no failed hands. These are inspection data, not a
full validated training corpus. Replay may repair omitted actions in other hands;
those repairs are counted rather than labeled as observed player decisions.

### Validated sample filtering

The decision exporter now keeps the first validated copy per `(site, hand ID)`.
Invalid copies do not prevent later valid copies from being retained. It rejects
whole hands with inserted betting decisions, missing essential game values,
unknown public board cards, or incomplete replay. Missing optional table, seats,
and winnings metadata is allowed; valid date/time and hand identity are required.
No missing game values are averaged. Source records remain unchanged.

The earlier structural audit is diagnostic; it has stricter optional-metadata
checks than the current decision exporter. Neither the audit nor the sample
export is a complete session classification or timezone-normalization pipeline.
The original sample command is still in-memory. Use `export-cached` for streaming
ZIP processing and persistent checkpoints.

## Cached streaming export

Start with a bounded run:

```sh
PYTHONPATH=src .venv/bin/python -m poker_bot.cli export-cached /Users/apmanasani/Downloads/phh-dataset-main.zip --max-files 3
```

Repeat the same command to reuse completed source files. Increase `--max-files`
to extend the sorted archive prefix, or omit it to process the whole archive.
The full archive has not yet been exported.

The report prints the actual output directory under ignored
`data/processed/cached-export/<processing-version>/<archive-sha256>/`. It contains:

- `cache.sqlite`: record hashes, accepted/rejected outcomes, cached decision rows,
  selected hand identities, and completed source-file checkpoints.
- `chunks/`: per-source-file decision and rejection logs.
- `decisions.jsonl`, action/street directories, and `rejections.jsonl`: rebuilt
  inspection views containing only the selected archive prefix.
- `summary.json`: counts, cache activity, scope, and completion status.

Only one hand's rows are buffered in RAM. Duplicate identities live in SQLite.
Archives and processing code (validator, features, exporter) are hashed, and the
PokerKit version is included, so changed inputs or logic use a fresh namespace.
Out-of-scope player counts/variants are counted at file level without replay-cache
entries. Rejected eligible records are cached with reasons; no missing game
values are imputed.

Chunks are flushed and synced before a file-level SQLite transaction commits.
On interruption, completed source files are reused; the unfinished file is redone.
Final views are reconstructed rather than appended, preventing duplicate output.
Read them only when `summary.json` says `status: complete`; `full_archive` tells
you whether all files were selected. Interrupted assembly leaves `status: building`.
A smaller `--max-files` rebuilds views for that smaller prefix, not all cached files.

Chunk hashes detect missing or damaged cache files; rebuild in a new output
folder if detected. A local file lock prevents concurrent writers for one cache.
The locking implementation supports macOS/Linux. Cache storage is persistent and
has no automatic eviction. It duplicates some data to make recovery straightforward.

Verified on three real source files: 2,998 records scanned, 1,030 accepted hands,
86 rejected hands, and 2,217 decision rows. River decisions include 45 calls and
3 raises. A second run reused all three checkpoints without revalidation.
This remains a bounded validation run, not a completed training dataset.
