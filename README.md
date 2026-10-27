# Isolating IO

A margin-call workflow for practicing the functional core / imperative shell
pattern.

The `main` branch contains the starting exercise in `margin_call/`, with IO
interleaved with business logic.

The solution is in the
[`engineered_solution` branch](https://github.com/renanreismartins/Imperative-Shell-Functional-Core/tree/engineered_solution),
also under `margin_call/`. Its pure valuation and decision functions live in
`core.py`, and `margin_call.py` handles IO and applies the decisions.

The IO dependencies in `margin_call/infra/` (`database.py`, `email_service.py`,
`market_data_api.py`) are stubs with canned data and logging. The example runs
locally without external services.

## margin_call

Use Python 3.10 or newer. Run from the repo root:

```bash
python3 -m margin_call
```

Install `pytest` in your Python environment, then run tests from the repo root:

```bash
python3 -m pip install pytest
python3 -m pytest margin_call/tests/
```

## Triggering a margin call

The canned account is healthy (margin level ≈ 3.3), so no margin call fires. To
see a database write and email alert, set AAPL's `margin_rate` to `1.5` in
`margin_call/infra/database.py` and rerun the example. This raises the margin
requirement above the portfolio value, bringing the margin level below `1.0`.
