# Isolating IO

Two implementations of the same margin-call workflow:

- `margin_call/` — IO interleaved with the business logic.
- `margin_call_functional_core/` — functional core / imperative shell: the
  decision logic lives in pure functions (`core.py`), all IO in `shell.py`.

The IO dependencies (`database.py`, `email_service.py`, `market_data_api.py`)
are stubs that only log what they would do.

## margin_call

Run (from the repo root):

```bash
python3 -m margin_call
```

Run tests (from the repo root):

```bash
python3 -m pytest margin_call/tests/
```

## margin_call_functional_core

Run:

```bash
cd margin_call_functional_core
python3 main.py
```

Run tests:

```bash
cd margin_call_functional_core
python3 -m pytest tests/
```

## Triggering a margin call

The canned account is healthy (margin level ≈ 3.2), so no margin call fires. To
see the margin-call branch (DB write + email), raise a `margin_rate` above 1.0
in the project's `infra/database.py`.
