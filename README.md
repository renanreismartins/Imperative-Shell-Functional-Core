# Isolating IO

A margin-call workflow structured around a functional core and an imperative shell.
The `engineered_solution` branch contains the implementation in `margin_call/`:

- `core.py` — pure functions that value a portfolio and decide whether to trigger
  a margin call, recover, or take no action.
- `models.py` — account state, snapshots, valuations, and decision types.
- `margin_call.py` — the imperative shell: reads the account and market prices,
  calls the core, applies the decision, saves changes, and sends alerts.
- `infra/` — database, email, and market-data stubs with canned data and logging.
- `tests/` — tests for account state, valuation, decisions, and error handling.

The stubs let the example run locally without external services. Database writes
and emails are logged.

## Running the example

Use Python 3.10 or newer. From the repo root:

```bash
python3 -m margin_call
```

## Running tests

Install `pytest` in your Python environment, then run from the repo root:

```bash
python3 -m pip install pytest
python3 -m pytest margin_call/tests/
```

## Triggering a margin call

The canned account is healthy (margin level ≈ 3.3), so no margin call fires. To
see a database write and email alert, set AAPL's `margin_rate` to `1.5` in
`margin_call/infra/database.py` and rerun the example. This raises the margin
requirement above the portfolio value, bringing the margin level below `1.0`.

## Workshop notes

[WORKSHOP_SESSION.md](margin_call/WORKSHOP_SESSION.md) records the refactoring
session.
