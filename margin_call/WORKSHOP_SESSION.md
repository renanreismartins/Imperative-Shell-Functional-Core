# User

For this session consider only the [margin_call](file:///Users/renanreismartins/personal-projects/isolating_io/margin_call) directory.

This is a tech workshop, I'm explaining the "functional core / imperative shell" pattern. 

Let's refactor the code to use the pattern. Let's draft one step at the time of the solution. Do not propose me anything beyond the step I'm in.

The code perform two read io operations, read an account 
<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="8" end_line="8">
<content>
    account = db.accounts.find_by_id(account_id)
</content>
</quoted_artifact>  and the price of the assets of the account 
<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="14" end_line="14">
<content>
    market_prices = market_data_api.get_latest_prices(asset_ids)
</content>
</quoted_artifact>  

Refactor so the method receive all the objects it needs, this way we do not need to mock the account loading and price gathering

# Assistant

## Step 1 — Push the reads out of the function

Move the two read operations to the caller, and have the function receive the data as parameters. The shell loads; the function computes and (for now) still writes.

```python
# margin_call.py
from margin_call.infra.database import db
from margin_call.infra.email_service import email_service
from margin_call.infra.market_data_api import market_data_api
from margin_call.models import Account


def process_margin_call(account_id: str) -> None:
    # imperative shell: do the reads here
    account = db.accounts.find_by_id(account_id)
    if not account:
        raise ValueError("Account not found")

    asset_ids = [p.asset_id for p in account.positions]
    market_prices = market_data_api.get_latest_prices(asset_ids)

    evaluate_margin(account, market_prices)


def evaluate_margin(account: Account, market_prices: dict[str, float]) -> None:
    total_portfolio_value = 0.0
    maintenance_margin_requirement = 0.0

    for position in account.positions:
        price = market_prices.get(position.asset_id, 0.0)
        position_value = position.quantity * price
        total_portfolio_value += position_value
        maintenance_margin_requirement += position_value * position.margin_rate

    if maintenance_margin_requirement == 0:
        return

    margin_level = total_portfolio_value / maintenance_margin_requirement

    if margin_level < 1.0:
        shortfall = maintenance_margin_requirement - total_portfolio_value
        account.status = 'MARGIN_CALL'
        account.margin_shortfall = shortfall
        db.accounts.save(account)
        email_service.send_margin_call_alert(account.email, shortfall)

    elif margin_level > 1.5 and account.status == 'MARGIN_CALL':
        account.status = 'HEALTHY'
        account.margin_shortfall = 0.0
        db.accounts.save(account)
```

What this buys you immediately: tests can call `evaluate_margin(account, prices)` directly, constructing `Account` and the prices dict in plain Python — no `@patch` for `db.accounts.find_by_id` or `market_data_api.get_latest_prices` anymore. The "account not found" check stays in the shell, where it belongs (it's an I/O concern).

The function still performs the write I/O (`db.accounts.save`, `email_service.send_...`) — that's for a later step.

# User

draft the test changes for this refactor

# Assistant

## Step 1 — Test changes

The read mocks disappear. Tests build an `Account` and a prices dict, and call `evaluate_margin` directly. Only the write side (`db.accounts.save`, `email_service`) still needs patching — that goes away in a later step.

```python
# tests/test_margin_call.py
from unittest.mock import patch

import pytest

from margin_call.margin_call import evaluate_margin, process_margin_call
from margin_call.models import Account, Position


def make_account(status="HEALTHY", positions=None):
    return Account(
        id="ACC-1",
        email="trader@example.com",
        status=status,
        positions=positions or [],
    )


# Only the writes need patching now.
@patch("margin_call.margin_call.email_service")
@patch("margin_call.margin_call.db")
class TestEvaluateMargin:

    def test_healthy_account_does_nothing(self, mock_db, mock_email):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
        ])

        evaluate_margin(account, {"AAPL": 100.0})

        assert account.status == "HEALTHY"
        mock_db.accounts.save.assert_not_called()
        mock_email.send_margin_call_alert.assert_not_called()

    def test_margin_call_triggered(self, mock_db, mock_email):
        # value = 10 * 100 = 1000; requirement = 1000 * 1.5 = 1500
        # margin_level = 1000 / 1500 < 1.0 -> shortfall = 500
        account = make_account(positions=[
            Position(asset_id="TSLA", quantity=10, margin_rate=1.5),
        ])

        evaluate_margin(account, {"TSLA": 100.0})

        assert account.status == "MARGIN_CALL"
        assert account.margin_shortfall == pytest.approx(500.0)
        mock_db.accounts.save.assert_called_once_with(account)
        mock_email.send_margin_call_alert.assert_called_once_with(
            "trader@example.com", pytest.approx(500.0)
        )

    def test_recovery_back_to_healthy(self, mock_db, mock_email):
        # value = 10 * 100 = 1000; requirement = 1000 * 0.5 = 500
        # margin_level = 2.0 > 1.5 and status is MARGIN_CALL -> recover
        account = make_account(status="MARGIN_CALL", positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])

        evaluate_margin(account, {"AAPL": 100.0})

        assert account.status == "HEALTHY"
        assert account.margin_shortfall == 0.0
        mock_db.accounts.save.assert_called_once_with(account)
        mock_email.send_margin_call_alert.assert_not_called()

    def test_zero_margin_requirement_returns_early(self, mock_db, mock_email):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.0),
        ])

        evaluate_margin(account, {"AAPL": 100.0})

        mock_db.accounts.save.assert_not_called()

    def test_missing_price_defaults_to_zero(self, mock_db, mock_email):
        # Price missing -> value 0, requirement 0 -> early return
        account = make_account(positions=[
            Position(asset_id="UNKNOWN", quantity=10, margin_rate=0.5),
        ])

        evaluate_margin(account, {})

        mock_db.accounts.save.assert_not_called()


# The "not found" case belongs to the shell, so it keeps its db patch.
@patch("margin_call.margin_call.email_service")
@patch("margin_call.margin_call.market_data_api")
@patch("margin_call.margin_call.db")
class TestProcessMarginCall:

    def test_account_not_found_raises(self, mock_db, mock_api, mock_email):
        mock_db.accounts.find_by_id.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            process_margin_call("MISSING")
```

Points worth highlighting in the workshop:

- The arrange sections shrank: no `mock_db.accounts.find_by_id.return_value = ...`, no `mock_api.get_latest_prices.return_value = ...`. Test data is plain constructors.
- The one test that still patches all three (`test_account_not_found_raises`) is the shell test — it's about I/O, so patching there is honest.
- The remaining `assert_called_once_with` / `assert_not_called` spy assertions are the smell that motivates the next step: extracting the decision into a pure function so tests can assert on a returned value instead of spying on writes.

# User

write the change and commit in the branch ai_solution

# Assistant

Current branch is already `ai_solution`, with uncommitted edits (comment text removed). I'll apply the step-1 refactor and test changes, run the tests, then commit.

# Assistant

Committed on `ai_solution` (2f48fcf). Tests pass — 6/6.

Changes:

- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" /> — `process_margin_call` keeps the two reads (account load, price fetch) and hands plain data to the new `evaluate_margin(account, market_prices)`.
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_margin_call.py" /> — five tests now call `evaluate_margin` directly with constructed data; only the write side is still patched. The "account not found" test stays as a shell test.

One note: I committed with the Devin bot identity via `-c` flags. If you'd rather have it under your own git identity, I can amend it.

# User

<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="19" end_line="31">
<content>
    total_portfolio_value = 0.0
    maintenance_margin_requirement = 0.0

    for position in account.positions:
        price = market_prices.get(position.asset_id, 0.0)
        position_value = position.quantity * price
        total_portfolio_value += position_value
        maintenance_margin_requirement += position_value * position.margin_rate

    if maintenance_margin_requirement == 0:
        return

    margin_level = total_portfolio_value / maintenance_margin_requirement
</content>
</quoted_artifact> this is part of our core domain, let's draft the extraction of this calculation

# Assistant

## Step 2 — Extract the calculation into a pure function

This block takes positions and prices in, and produces three numbers. That's a pure function. Give the result a name with a small dataclass so the "no requirement" case is explicit instead of an early `return`:

```python
# models.py (or margin_call.py, your call for the workshop)
@dataclass(frozen=True)
class PortfolioValuation:
    total_value: float
    margin_requirement: float

    @property
    def margin_level(self) -> float | None:
        if self.margin_requirement == 0:
            return None
        return self.total_value / self.margin_requirement
```

```python
# margin_call.py — pure core, no imports from infra
def value_portfolio(
    positions: list[Position], market_prices: dict[str, float]
) -> PortfolioValuation:
    total_value = 0.0
    margin_requirement = 0.0

    for position in positions:
        price = market_prices.get(position.asset_id, 0.0)
        position_value = position.quantity * price
        total_value += position_value
        margin_requirement += position_value * position.margin_rate

    return PortfolioValuation(total_value, margin_requirement)
```

`evaluate_margin` shrinks to:

```python
def evaluate_margin(account: Account, market_prices: dict[str, float]) -> None:
    valuation = value_portfolio(account.positions, market_prices)

    if valuation.margin_level is None:
        return

    if valuation.margin_level < 1.0:
        shortfall = valuation.margin_requirement - valuation.total_value
        account.status = 'MARGIN_CALL'
        account.margin_shortfall = shortfall
        db.accounts.save(account)
        email_service.send_margin_call_alert(account.email, shortfall)

    elif valuation.margin_level > 1.5 and account.status == 'MARGIN_CALL':
        account.status = 'HEALTHY'
        account.margin_shortfall = 0.0
        db.accounts.save(account)
```

Workshop talking points:

- `value_portfolio` takes `positions`, the minimum it needs — a sign it's drifting toward the core: dependencies get narrower as logic gets purer.
- It's testable with zero mocks: pass positions and a dict, assert on the returned numbers. First tests in the suite with no `@patch` at all.
- Returning `PortfolioValuation` instead of a tuple makes the zero-requirement case (`margin_level is None`) a domain fact rather than a buried `if`.

Design choices you might want to weigh in on: frozen dataclass vs. plain function returning a tuple, and whether `margin_level` belongs as a property or stays inline in `evaluate_margin`. I went with the dataclass + property since it gives the domain concept a name — fits the workshop narrative.

# User

draft the tests

# Assistant

## Step 2 — Tests for the pure core

New test class, no `@patch` anywhere — construct positions and a price dict, assert on the returned values:

```python
from margin_call.margin_call import value_portfolio


class TestValuePortfolio:

    def test_values_single_position(self):
        positions = [Position(asset_id="AAPL", quantity=10, margin_rate=0.25)]

        valuation = value_portfolio(positions, {"AAPL": 100.0})

        assert valuation.total_value == pytest.approx(1000.0)
        assert valuation.margin_requirement == pytest.approx(250.0)
        assert valuation.margin_level == pytest.approx(4.0)

    def test_sums_multiple_positions(self):
        positions = [
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
            Position(asset_id="TSLA", quantity=5, margin_rate=0.5),
        ]

        valuation = value_portfolio(positions, {"AAPL": 100.0, "TSLA": 200.0})

        # AAPL: 1000 (req 250), TSLA: 1000 (req 500)
        assert valuation.total_value == pytest.approx(2000.0)
        assert valuation.margin_requirement == pytest.approx(750.0)

    def test_missing_price_defaults_to_zero(self):
        positions = [Position(asset_id="UNKNOWN", quantity=10, margin_rate=0.5)]

        valuation = value_portfolio(positions, {})

        assert valuation.total_value == 0.0
        assert valuation.margin_requirement == 0.0

    def test_no_positions(self):
        valuation = value_portfolio([], {})

        assert valuation.total_value == 0.0
        assert valuation.margin_requirement == 0.0

    def test_margin_level_is_none_when_no_requirement(self):
        positions = [Position(asset_id="AAPL", quantity=10, margin_rate=0.0)]

        valuation = value_portfolio(positions, {"AAPL": 100.0})

        assert valuation.margin_level is None
```

And two existing tests in `TestEvaluateMargin` get simpler in meaning — `test_zero_margin_requirement_returns_early` and `test_missing_price_defaults_to_zero` were always arithmetic tests wearing I/O clothing. Their real substance now lives in `TestValuePortfolio` (`test_margin_level_is_none_when_no_requirement`, `test_missing_price_defaults_to_zero`). You can keep one thin version in `TestEvaluateMargin` to pin the "no requirement → no save" behavior and drop the duplicate:

```python
    def test_zero_margin_requirement_does_nothing(self, mock_db, mock_email):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.0),
        ])

        evaluate_margin(account, {"AAPL": 100.0})

        mock_db.accounts.save.assert_not_called()
```

Workshop talking point: compare the arrange/assert of `TestValuePortfolio` with the original suite — plain data in, plain data out, and every assertion is on a value. The edge cases (missing price, empty portfolio, zero rate) are now cheap to enumerate; before, each one cost three mock setups.

# User

write the changes

# Assistant

Now the tests:

# Assistant

All 10 tests pass. Changes written:

- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/models.py" lines="11-20" /> — `PortfolioValuation` frozen dataclass with the `margin_level` property (`None` when there's no requirement).
- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" lines="18-30" /> — `value_portfolio(positions, market_prices)` pure function; `evaluate_margin` now just consumes the valuation and handles the decisions/writes.
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_margin_call.py" /> — new `TestValuePortfolio` class with five mock-free tests; the two arithmetic tests were removed from `TestEvaluateMargin`, leaving one thin `test_zero_margin_requirement_does_nothing` to pin the no-save behavior.

Want me to commit this on `ai_solution`?

# User

Lint errors detected.

# Assistant

Fixed. The import line exceeded the line length, so ruff wrapped it into a parenthesized block. Tests still pass (10/10).

# User

<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="42" end_line="43">
<content>
        account.status = 'MARGIN_CALL'
        account.margin_shortfall = shortfall
</content>
</quoted_artifact> and 
<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="49" end_line="50">
<content>
        account.status = 'HEALTHY'
        account.margin_shortfall = 0.0
</content>
</quoted_artifact> seems like "anemic model" let's move the behaviour and data into the object.

# Assistant

## Step 3 — Move the state transitions into `Account`

The two mutation pairs are domain state transitions with names: "enter margin call" and "recover". Give `Account` those methods, and fold the guard conditions in so the rules live with the data:

```python
# models.py
@dataclass
class Account:
    id: str
    email: str
    status: str = "HEALTHY"
    margin_shortfall: float = 0.0
    positions: list[Position] = field(default_factory=list)

    def enter_margin_call(self, shortfall: float) -> None:
        self.status = "MARGIN_CALL"
        self.margin_shortfall = shortfall

    def recover(self) -> None:
        self.status = "HEALTHY"
        self.margin_shortfall = 0.0

    @property
    def in_margin_call(self) -> bool:
        return self.status == "MARGIN_CALL"
```

`evaluate_margin` now reads as the policy it is:

```python
def evaluate_margin(account: Account, market_prices: dict[str, float]) -> None:
    valuation = value_portfolio(account.positions, market_prices)

    if valuation.margin_level is None:
        return

    if valuation.margin_level < 1.0:
        shortfall = valuation.margin_requirement - valuation.total_value
        account.enter_margin_call(shortfall)
        db.accounts.save(account)
        email_service.send_margin_call_alert(account.email, shortfall)

    elif valuation.margin_level > 1.5 and account.in_margin_call:
        account.recover()
        db.accounts.save(account)
```

Workshop talking points:

- `Account` stops being a bag of fields other code pokes at — the valid transitions are now the model's API, and the magic strings `'MARGIN_CALL'` / `'HEALTHY'` are encapsulated behind it.
- These methods are still pure in the FC/IS sense: they mutate in-memory state only, no I/O. The core of the model grew; the shell didn't.
- `in_margin_call` replaces the string comparison at the call site, so the shell no longer knows how status is represented.

Two scoping decisions I deliberately left out of this step, in case you want them as discussion prompts: making `status` an `Enum` instead of a string, and pushing the threshold rules (`< 1.0`, `> 1.5`) into the model too. Both are natural follow-ups.

# User

change the status to an enum.

# Assistant

## Step 3b — `status` as an `Enum`

```python
# models.py
from dataclasses import dataclass, field
from enum import Enum


class AccountStatus(Enum):
    HEALTHY = "HEALTHY"
    MARGIN_CALL = "MARGIN_CALL"


@dataclass
class Account:
    id: str
    email: str
    status: AccountStatus = AccountStatus.HEALTHY
    margin_shortfall: float = 0.0
    positions: list[Position] = field(default_factory=list)

    def enter_margin_call(self, shortfall: float) -> None:
        self.status = AccountStatus.MARGIN_CALL
        self.margin_shortfall = shortfall

    def recover(self) -> None:
        self.status = AccountStatus.HEALTHY
        self.margin_shortfall = 0.0

    @property
    def in_margin_call(self) -> bool:
        return self.status is AccountStatus.MARGIN_CALL
```

`evaluate_margin` is untouched — it already talks through `enter_margin_call` / `recover` / `in_margin_call`. That's the payoff of the previous step: the representation change is invisible to the shell.

Tests change in two places:

```python
from margin_call.models import Account, AccountStatus, Position


def make_account(status=AccountStatus.HEALTHY, positions=None):
    ...
```

and assertions compare against the enum:

```python
assert account.status is AccountStatus.MARGIN_CALL
# ...
account = make_account(status=AccountStatus.MARGIN_CALL, positions=[...])
assert account.status is AccountStatus.HEALTHY
```

Workshop talking points:

- Typos like `'MARGIN_CAL'` were silent bugs with strings; with the enum they're `AttributeError`s at import time.
- `str`-valued enum members keep serialization trivial if the DB layer stores strings (`account.status.value`). If you want `account.status == "HEALTHY"` to keep working during a migration, `class AccountStatus(str, Enum)` is the compatibility trick — I'd skip it here since we control all call sites.
- With the methods from the previous step, only `models.py` and the test fixtures knew about the strings, so the blast radius of this change is two files.

Say the word and I'll write it.

# User

draft the tests

# Assistant

## Step 3 — Tests

New pure test class for the model's transitions — no mocks, state in → state out:

```python
from margin_call.models import Account, AccountStatus, Position


class TestAccountTransitions:

    def test_new_account_is_healthy(self):
        account = make_account()

        assert account.status is AccountStatus.HEALTHY
        assert not account.in_margin_call

    def test_enter_margin_call(self):
        account = make_account()

        account.enter_margin_call(500.0)

        assert account.status is AccountStatus.MARGIN_CALL
        assert account.in_margin_call
        assert account.margin_shortfall == 500.0

    def test_recover(self):
        account = make_account(status=AccountStatus.MARGIN_CALL)
        account.margin_shortfall = 500.0

        account.recover()

        assert account.status is AccountStatus.HEALTHY
        assert not account.in_margin_call
        assert account.margin_shortfall == 0.0
```

`make_account` takes the enum as its default:

```python
def make_account(status=AccountStatus.HEALTHY, positions=None):
    return Account(
        id="ACC-1",
        email="trader@example.com",
        status=status,
        positions=positions or [],
    )
```

And the three `TestEvaluateMargin` tests that touch status get updated to the enum:

```python
    def test_healthy_account_does_nothing(self, mock_db, mock_email):
        ...
        assert account.status is AccountStatus.HEALTHY

    def test_margin_call_triggered(self, mock_db, mock_email):
        ...
        assert account.status is AccountStatus.MARGIN_CALL
        assert account.margin_shortfall == pytest.approx(500.0)
        ...

    def test_recovery_back_to_healthy(self, mock_db, mock_email):
        account = make_account(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])
        ...
        assert account.status is AccountStatus.HEALTHY
```

`TestValuePortfolio` and `TestProcessMarginCall` are untouched — they never knew about status strings.

Workshop talking point: `TestAccountTransitions` documents the domain vocabulary directly — "enter margin call", "recover" — and the suite now has three mock-free classes against one shrinking mocked one. The remaining spy assertions in `TestEvaluateMargin` (`save.assert_called_once_with`, `send_margin_call_alert.assert_called_once_with`) are the last smell, which sets up the final step: making the core return a decision and letting the shell execute it.

# User

write the changes

# Assistant

Now the tests:

# Assistant

All 13 tests pass, ruff clean. Changes:

- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/models.py" lines="5-7" /> — `AccountStatus` enum.
- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/models.py" lines="37-47" /> — `Account.enter_margin_call()`, `Account.recover()`, and the `in_margin_call` property; `status` typed as `AccountStatus`.
- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" lines="39-49" /> — `evaluate_margin` now calls the transitions instead of poking fields; no string comparison left.
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_margin_call.py" /> — new mock-free `TestAccountTransitions` class; existing assertions use the enum.

Want me to commit this on `ai_solution`?

# User

commit the previous change and leave this last one

# Assistant

The two steps are interleaved in the same files, so I'll stash the enum/Account-behavior changes aside, write the step-2-only versions, commit, then restore.

# Assistant

Now revert the three files to their step-2 state (pure `value_portfolio` extraction, strings still, no Account methods):

# Assistant

Now restore the step-3 (enum + Account behavior) changes as uncommitted work:

# Assistant

Done.

- Committed `5bbf2e9 Extract portfolio valuation into a pure function` — the step-2 state (`value_portfolio`, `PortfolioValuation`, mock-free `TestValuePortfolio`). Tests passed at that point (10/10).
- The enum + `Account` behavior changes (step 3) are back in the working tree, uncommitted, with all 13 tests passing.

# User

commit the latest changes

# Assistant

Committed `2d68ecb Move margin state transitions into Account` on `ai_solution`. The branch now has the three steps as separate commits:

```
2d68ecb Move margin state transitions into Account
5bbf2e9 Extract portfolio valuation into a pure function
2f48fcf Push read I/O out of margin evaluation
```

# User

We have the side effects 
<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="43" end_line="45">
<content>
        db.accounts.save(account)

        email_service.send_margin_call_alert(account.email, shortfall)
</content>
</quoted_artifact> , 
<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="49" end_line="49">
<content>
        db.accounts.save(account)
</content>
</quoted_artifact> 

those could be replaced by decision return values

# Assistant

## Step 4 — Return a decision instead of performing effects

Make the core answer one question — "what should happen to this account?" — as a value. The shell interprets it. A small sum type names the outcomes:

```python
# models.py (or a decisions module)
@dataclass(frozen=True)
class TriggerMarginCall:
    shortfall: float


@dataclass(frozen=True)
class Recover:
    pass


@dataclass(frozen=True)
class NoAction:
    pass


MarginDecision = TriggerMarginCall | Recover | NoAction
```

The core becomes fully pure — no infra imports, no mutation, just data in, decision out:

```python
# margin_call.py — functional core
def decide_margin_action(
    account: Account, valuation: PortfolioValuation
) -> MarginDecision:
    if valuation.margin_level is None:
        return NoAction()

    if valuation.margin_level < 1.0:
        return TriggerMarginCall(
            shortfall=valuation.margin_requirement - valuation.total_value
        )

    if valuation.margin_level > 1.5 and account.in_margin_call:
        return Recover()

    return NoAction()
```

The shell does all the I/O and interprets the decision; `evaluate_margin` dissolves into it:

```python
# margin_call.py — imperative shell
def process_margin_call(account_id: str) -> None:
    account = db.accounts.find_by_id(account_id)
    if not account:
        raise ValueError("Account not found")

    asset_ids = [p.asset_id for p in account.positions]
    market_prices = market_data_api.get_latest_prices(asset_ids)

    valuation = value_portfolio(account.positions, market_prices)
    decision = decide_margin_action(account, valuation)

    match decision:
        case TriggerMarginCall(shortfall=shortfall):
            account.enter_margin_call(shortfall)
            db.accounts.save(account)
            email_service.send_margin_call_alert(account.email, shortfall)
        case Recover():
            account.recover()
            db.accounts.save(account)
        case NoAction():
            pass
```

Workshop talking points — this is the payoff slide:

- The core is now 100% I/O-free: `value_portfolio`, `decide_margin_action`, and the `Account` transitions. All the business rules (thresholds, shortfall math, recovery hysteresis) are testable by asserting on returned values — zero `@patch`, zero spy assertions.
- The shell is one function you can read top to bottom: load → compute → decide → execute. It contains no business logic, so it needs at most one thin integration test.
- The decision is a value, so it's loggable, serializable, and auditable for free — "why did this account get an email?" has an inspectable answer.
- Hidden rule made explicit: the old `elif` meant "healthy-but-not-recovering accounts do nothing". `NoAction()` gives that outcome a name, and the fall-through case (`1.0 ≤ level ≤ 1.5`, or high level but already healthy) is now visible in tests.

One trade-off to name for the audience: the shell's `match` can silently miss a new decision type. Python can't exhaustiveness-check a `match` at runtime, though adding `case _: raise` or using a type checker with the union covers it.

Want me to draft the tests next?

# User

draft the tests

# Assistant

## Step 4 — Tests

`TestEvaluateMargin` dies. Its replacement, `TestDecideMarginAction`, is pure — every scenario is data in, decision value out, no `@patch`:

```python
from margin_call.margin_call import (
    decide_margin_action,
    process_margin_call,
    value_portfolio,
)
from margin_call.models import (
    Account,
    AccountStatus,
    NoAction,
    Position,
    Recover,
    TriggerMarginCall,
)


# Pure core: the decision policy, no mocks.
class TestDecideMarginAction:

    def test_healthy_account_no_action(self):
        # level = 1000 / 250 = 4.0
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == NoAction()

    def test_below_requirement_triggers_margin_call(self):
        # value 1000, requirement 1500 -> shortfall 500
        account = make_account(positions=[
            Position(asset_id="TSLA", quantity=10, margin_rate=1.5),
        ])
        valuation = value_portfolio(account.positions, {"TSLA": 100.0})

        decision = decide_margin_action(account, valuation)

        assert decision == TriggerMarginCall(shortfall=pytest.approx(500.0))

    def test_recovers_above_threshold_when_in_margin_call(self):
        # level = 1000 / 500 = 2.0 > 1.5
        account = make_account(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == Recover()

    def test_high_level_but_already_healthy_no_action(self):
        # Same valuation as recovery, but status is HEALTHY
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == NoAction()

    def test_in_hysteresis_band_no_action(self):
        # level = 1000 / 800 = 1.25: above 1.0, below 1.5 -> stay put
        account = make_account(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.8),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == NoAction()

    def test_no_margin_requirement_no_action(self):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.0),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == NoAction()
```

The shell keeps a thin test class — the only place patches remain, checking wiring end to end:

```python
@patch("margin_call.margin_call.email_service")
@patch("margin_call.margin_call.market_data_api")
@patch("margin_call.margin_call.db")
class TestProcessMarginCall:

    def test_account_not_found_raises(self, mock_db, mock_api, mock_email):
        mock_db.accounts.find_by_id.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            process_margin_call("MISSING")

    def test_margin_call_end_to_end(self, mock_db, mock_api, mock_email):
        account = make_account(positions=[
            Position(asset_id="TSLA", quantity=10, margin_rate=1.5),
        ])
        mock_db.accounts.find_by_id.return_value = account
        mock_api.get_latest_prices.return_value = {"TSLA": 100.0}

        process_margin_call("ACC-1")

        assert account.status is AccountStatus.MARGIN_CALL
        assert account.margin_shortfall == pytest.approx(500.0)
        mock_db.accounts.save.assert_called_once_with(account)
        mock_email.send_margin_call_alert.assert_called_once_with(
            "trader@example.com", pytest.approx(500.0)
        )

    def test_recovery_end_to_end(self, mock_db, mock_api, mock_email):
        account = make_account(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])
        mock_db.accounts.find_by_id.return_value = account
        mock_api.get_latest_prices.return_value = {"AAPL": 100.0}

        process_margin_call("ACC-1")

        assert account.status is AccountStatus.HEALTHY
        mock_db.accounts.save.assert_called_once_with(account)
        mock_email.send_margin_call_alert.assert_not_called()
```

`TestValuePortfolio` and `TestAccountTransitions` stay as they are.

Workshop talking points:

- Frozen dataclasses give value equality, so a whole decision is one `==` assertion — `decision == TriggerMarginCall(shortfall=...)` reads like the spec.
- Two scenarios the old suite couldn't express cheaply are now one-liners: the hysteresis band (`1.0 ≤ level ≤ 1.5`) and "high level but already healthy". Pure functions make edge-case enumeration nearly free.
- The mock count tells the story: step 0 had three patches on every test; now patches exist only in the two or three shell tests, which verify wiring — the business rules never see a mock.

# User

write the changes. no need to implement the new unit tests in TestProcessMarginCall

# Assistant

Now the tests — replace `TestEvaluateMargin` with the pure `TestDecideMarginAction`, keeping `TestProcessMarginCall` as is:

# Assistant

All 15 tests pass, ruff clean. Changes:

- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/models.py" lines="29-44" /> — `TriggerMarginCall`, `Recover`, `NoAction` and the `MarginDecision` union.
- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" lines="53-67" /> — `decide_margin_action` is pure: valuation + account in, decision out. `evaluate_margin` is gone.
- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" lines="15-35" /> — `process_margin_call` is now the whole shell: load → value → decide → `match` to execute the effects.
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_margin_call.py" /> — `TestEvaluateMargin` replaced by the mock-free `TestDecideMarginAction` (6 scenarios, including the hysteresis band and already-healthy cases the old suite didn't cover). `TestProcessMarginCall` untouched per your instruction.

The suite now has three pure test classes and one shell class with the only remaining patches. Want me to commit?

# User

commit

# Assistant

Committed `f3fc99b`. The branch now tells the whole workshop story in four commits:

```
f3fc99b Return margin decisions instead of performing effects
2d68ecb Move margin state transitions into Account
5bbf2e9 Extract portfolio valuation into a pure function
2f48fcf Push read I/O out of margin evaluation
```

# User

extract the tests into different files

# Assistant

I'll split by subject under test — one file per test class — with the shared `make_account` helper in a `factories.py`:

# Assistant

All 15 tests pass, ruff clean. `test_margin_call.py` is split into:

- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/factories.py" /> — shared `make_account` helper
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_account.py" /> — `TestAccountTransitions`
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_value_portfolio.py" /> — `TestValuePortfolio`
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_decide_margin_action.py" /> — `TestDecideMarginAction`
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_process_margin_call.py" /> — `TestProcessMarginCall` (the only file importing `unittest.mock`)

Nice workshop artifact: the file layout now mirrors the architecture — three mock-free core files, one shell file. Want me to commit?

# User

commit

# Assistant

Committed `5fe6ada Split tests into one file per subject` on `ai_solution`.

# User

extract [margin_call.py](file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py) into the shell and move the pure functions to another file

# Assistant

I'll move the two pure functions into a new `core.py`, leaving `margin_call.py` as the shell, and update the test imports:

# Assistant

All 15 tests pass, ruff clean. The module layout now states the pattern:

- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/core.py" /> — `value_portfolio` and `decide_margin_action`; imports only from `models`, no infra.
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" /> — the shell: the only module importing `infra`, holding just `process_margin_call`.
- Core test files now import from `margin_call.core`; the shell test is unchanged.

Nice closing point for the workshop: the import graph is now the architecture diagram — `core.py` can't do I/O because it can't even see the infra modules. Commit?

# User

commit without the [WORKSHOP_SESSION.md](file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/WORKSHOP_SESSION.md) 

# Assistant

Committed `b098dc7 Split core and shell into separate modules`. `WORKSHOP_SESSION.md` remains untracked in the working tree.

# User

<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="11" end_line="11">
<content>
        raise ValueError(&quot;Account not found&quot;)
</content>
</quoted_artifact> use a specific exception instead of a generic one

# Assistant

All 15 tests pass, ruff clean.

- `AccountNotFoundError` is defined next to its raise site in <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" lines="8-17" />, carrying the `account_id` and including it in the message.
- The shell test asserts the specific exception and matches on the id: <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/tests/test_process_margin_call.py" lines="17-18" />.

Commit?

# User

do not embbed highly variable, dynamic data directly into the exception string is a major observability anti-pattern. remove the variable

# Assistant

Done — the message is the constant `"Account not found"` (groupable by error trackers), and the id lives only in the structured `account_id` attribute. The test now asserts on that attribute instead of matching the message. 15/15 passing, ruff clean.

Commit?

# User

commit

# Assistant

Committed `bc50609 Raise AccountNotFoundError with structured account_id` on `ai_solution`.

# User

should we decouple the core from the ORM with immutable inputs (assuming 
<quoted_artifact kind="file" path="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" version_ref="file:///Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" start_line="15" end_line="15">
<content>
    account = db.accounts.find_by_id(account_id)
</content>
</quoted_artifact> returns an orm managed object) ?

# Assistant

Yes — if `find_by_id` returned an ORM-managed object, the current design has a real leak, and it's worth a step. But there's a cheap version and an expensive version.

## Why the leak matters

An ORM entity passed into the core breaks purity in ways that don't show in the signature:

- **Hidden I/O**: `account.positions` on a lazy relationship fires a query. Your "pure" `value_portfolio` now does I/O depending on what the shell loaded — and explodes with a detached-session error in exactly the contexts (background jobs, tests) where you relied on purity.
- **Hidden writes**: with a unit-of-work ORM (SQLAlchemy), *any* attribute mutation marks the object dirty; a later flush persists it whether or not the shell decided to save. `account.enter_margin_call()` as currently written would write to the DB implicitly — the decision/effect separation we built in step 4 would be partially fiction.
- **Identity leakage**: the core can traverse to anything reachable from the entity graph, so its true dependency surface is unknowable from its parameters.

## The cheap version: narrow the inputs

Look at what the core actually needs:

- `value_portfolio` needs `positions` — already takes them, and `Position` is a plain dataclass.
- `decide_margin_action` needs the valuation and one bit: `account.in_margin_call`.

So the minimal decoupling is to stop passing `Account` into the core at all:

```python
def decide_margin_action(
    valuation: PortfolioValuation, *, in_margin_call: bool
) -> MarginDecision:
    ...
```

The shell maps at the boundary (`in_margin_call=account.status is ...`), and the core's dependency surface is now exactly its parameters. No mapping layer, no duplicate model. For this codebase I'd do this — it also removes the slightly odd fact that `decide_margin_action` takes a whole mutable `Account` and reads one property.

## The expensive version: immutable snapshot

If the core genuinely needs many account fields, map to a frozen domain type at the boundary:

```python
@dataclass(frozen=True)
class AccountSnapshot:
    status: AccountStatus
    positions: tuple[Position, ...]   # tuple, not list
```

with the shell doing `snapshot = to_snapshot(orm_account)` right after the read. This gives the strongest guarantee — the core *cannot* trigger lazy loads or dirty the session, enforced by construction — at the cost of a mapping function and a second model to keep in sync. The `tuple` matters: `frozen=True` with a `list` field is only shallowly immutable.

## Where the state transitions go

Note what this implies for step 3's `enter_margin_call`/`recover`: with an ORM, mutating the entity *is* an effect, so those transitions belong in the shell applied to the ORM object (as the `match` already does) — which is exactly where they live. The core decides; the shell mutates the managed object and saves. That boundary survives unchanged.

**Recommendation for the workshop**: do the cheap version as a step, and present the snapshot version as the slide for "what if this were SQLAlchemy" — it makes the lazy-loading and dirty-tracking traps concrete without forcing the mapping boilerplate into a toy codebase. Want me to draft the cheap version?

# User

draft the expensive version as it is closer to a real scenario.

# Assistant

## Step 5 — Immutable snapshot at the boundary

Map the (hypothetically ORM-managed) `Account` to a frozen domain snapshot right after the read. The core only ever sees the snapshot.

```python
# models.py
@dataclass(frozen=True)
class AccountSnapshot:
    status: AccountStatus
    positions: tuple[Position, ...]

    @property
    def in_margin_call(self) -> bool:
        return self.status is AccountStatus.MARGIN_CALL

    @classmethod
    def of(cls, account: Account) -> "AccountSnapshot":
        return cls(status=account.status, positions=tuple(account.positions))
```

Notes on the shape:

- `positions` is a `tuple` — `frozen=True` with a `list` field is only shallowly immutable, and the tuple is what actually stops the core from appending or (with a real ORM) triggering collection loads mid-computation.
- `AccountSnapshot.of(account)` is the single mapping point. With a real ORM this is where every lazy load happens, deliberately and visibly, while the session is live. After this line the core can't touch the session.
- `in_margin_call` moves to the snapshot (read side); `enter_margin_call`/`recover` stay on `Account` (write side). The split mirrors the pattern: snapshot = facts for deciding, entity = state to mutate.
- No `email`/`id` on the snapshot — the core doesn't decide *who* to notify, only *what* should happen. The shell still has the entity for the effects.

The core swaps `Account` for the snapshot:

```python
# core.py — no longer imports Account
def value_portfolio(
    positions: tuple[Position, ...], market_prices: dict[str, float]
) -> PortfolioValuation:
    ...  # body unchanged


def decide_margin_action(
    snapshot: AccountSnapshot, valuation: PortfolioValuation
) -> MarginDecision:
    if valuation.margin_level is None:
        return NoAction()

    if valuation.margin_level < 1.0:
        return TriggerMarginCall(
            shortfall=valuation.margin_requirement - valuation.total_value
        )

    if valuation.margin_level > 1.5 and snapshot.in_margin_call:
        return Recover()

    return NoAction()
```

The shell maps once, right after the read:

```python
# margin_call.py
def process_margin_call(account_id: str) -> None:
    account = db.accounts.find_by_id(account_id)
    if not account:
        raise AccountNotFoundError(account_id)

    snapshot = AccountSnapshot.of(account)
    market_prices = market_data_api.get_latest_prices(
        [p.asset_id for p in snapshot.positions]
    )

    valuation = value_portfolio(snapshot.positions, market_prices)
    decision = decide_margin_action(snapshot, valuation)

    match decision:
        case TriggerMarginCall(shortfall=shortfall):
            account.enter_margin_call(shortfall)
            db.accounts.save(account)
            email_service.send_margin_call_alert(account.email, shortfall)
        case Recover():
            account.recover()
            db.accounts.save(account)
        case NoAction():
            pass
```

Test impact is small: `factories.py` gains a `make_snapshot(...)` helper (or `AccountSnapshot.of(make_account(...))`), `test_decide_margin_action.py` passes snapshots instead of accounts, `test_value_portfolio.py` passes tuples. `TestAccountTransitions` and the shell test are untouched.

Workshop talking points:

- The guarantee is now structural: the core can't lazy-load, can't dirty the session, can't reach the entity graph — not because we're disciplined, but because the snapshot physically contains only what was copied out.
- Line 20 (`snapshot = AccountSnapshot.of(account)`) is the boundary made visible: everything above and below it is shell; everything that takes the snapshot is core.
- The honest cost to name: a second model and a mapping function that must evolve with `Account`. That's the price of the guarantee, and in a toy codebase it looks like pure overhead — which is exactly why it's worth showing against the "real ORM" framing.

Want me to write it?

# User

draft the changes on the tests

# Assistant

## Step 5 — Test changes

`factories.py` gains a snapshot factory alongside the account one:

```python
# tests/factories.py
from margin_call.models import Account, AccountSnapshot, AccountStatus


def make_account(status=AccountStatus.HEALTHY, positions=None):
    return Account(
        id="ACC-1",
        email="trader@example.com",
        status=status,
        positions=positions or [],
    )


def make_snapshot(status=AccountStatus.HEALTHY, positions=()):
    return AccountSnapshot(status=status, positions=tuple(positions))
```

`test_decide_margin_action.py` swaps accounts for snapshots — the diff is almost mechanical (`make_account` → `make_snapshot`, `account` → `snapshot`):

```python
from margin_call.core import decide_margin_action, value_portfolio
from margin_call.models import (
    AccountStatus,
    NoAction,
    Position,
    Recover,
    TriggerMarginCall,
)
from margin_call.tests.factories import make_snapshot


# Pure core: the decision policy, no mocks.
class TestDecideMarginAction:

    def test_healthy_account_no_action(self):
        # level = 1000 / 250 = 4.0
        snapshot = make_snapshot(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
        ])
        valuation = value_portfolio(snapshot.positions, {"AAPL": 100.0})

        assert decide_margin_action(snapshot, valuation) == NoAction()

    def test_below_requirement_triggers_margin_call(self):
        # value 1000, requirement 1500 -> shortfall 500
        snapshot = make_snapshot(positions=[
            Position(asset_id="TSLA", quantity=10, margin_rate=1.5),
        ])
        valuation = value_portfolio(snapshot.positions, {"TSLA": 100.0})

        decision = decide_margin_action(snapshot, valuation)

        assert decision == TriggerMarginCall(shortfall=pytest.approx(500.0))

    def test_recovers_above_threshold_when_in_margin_call(self):
        # level = 1000 / 500 = 2.0 > 1.5
        snapshot = make_snapshot(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])
        valuation = value_portfolio(snapshot.positions, {"AAPL": 100.0})

        assert decide_margin_action(snapshot, valuation) == Recover()

    # ... same pattern for the hysteresis-band, already-healthy,
    # and no-requirement cases
```

`test_value_portfolio.py` passes tuples instead of lists:

```python
    def test_values_single_position(self):
        positions = (Position(asset_id="AAPL", quantity=10, margin_rate=0.25),)

        valuation = value_portfolio(positions, {"AAPL": 100.0})
        ...

    def test_no_positions(self):
        valuation = value_portfolio((), {})
        ...
```

A small new test pins the mapping itself — the one piece of new logic:

```python
# tests/test_account.py (or a new test_snapshot.py)
class TestAccountSnapshot:

    def test_snapshot_captures_status_and_positions(self):
        account = make_account(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])

        snapshot = AccountSnapshot.of(account)

        assert snapshot.status is AccountStatus.MARGIN_CALL
        assert snapshot.in_margin_call
        assert snapshot.positions == tuple(account.positions)

    def test_snapshot_is_detached_from_later_mutation(self):
        account = make_account()
        snapshot = AccountSnapshot.of(account)

        account.enter_margin_call(500.0)
        account.positions.append(
            Position(asset_id="TSLA", quantity=1, margin_rate=0.5)
        )

        assert snapshot.status is AccountStatus.HEALTHY
        assert snapshot.positions == ()
```

Untouched: `TestAccountTransitions` (the entity's write side) and `TestProcessMarginCall` (the shell).

Workshop talking points:

- `test_snapshot_is_detached_from_later_mutation` is the demo of the guarantee: mutate the entity after snapshotting and the snapshot doesn't move. With a real ORM that's exactly the "stale read vs. dirty session" conversation.
- The decision tests got *simpler* inputs: no `id`, no `email` — the factory only carries what the policy reads, which documents the policy's true dependency surface.
- Mechanical diff size is the honest cost on the test side: one rename sweep. The new logic worth testing is just the mapping.

# User

write and commit

# Assistant

Now the tests — factories, decision tests, valuation tuples, and the snapshot tests:

# Assistant

Now the valuation tests (tuples) and the snapshot tests:

# Assistant

Committed `d8a38f6`. All 17 tests pass, ruff clean.

- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/models.py" lines="68-80" /> — `AccountSnapshot` (frozen, `tuple` positions) with `in_margin_call` and the `of()` mapping.
- <ref_file file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/core.py" /> — no longer imports `Account`; `value_portfolio` takes a tuple, `decide_margin_action` takes the snapshot.
- <ref_snippet file="/Users/renanreismartins/personal-projects/isolating_io/margin_call/margin_call.py" lines="25-30" /> — the shell maps once right after the read; the entity is only touched again inside the `match` for transitions and effects.
- Tests: `make_snapshot` factory, decision tests on snapshots, valuation tests on tuples, and two new `TestAccountSnapshot` tests — including the detachment demo where mutating the entity after snapshotting leaves the snapshot unchanged.
