# Slack Table Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slack receives the six tabular reports as native Block Kit tables and every other report with a bold title, while GroupMe and Discord output stays byte-identical.

**Architecture:** A new `gamedaybot/espn/tables.py` turns league data into a small `Table` value object; a new pure module `gamedaybot/chat/slack_format.py` turns a `Table` or a text report into Block Kit blocks; `Slack.send_blocks` posts them. `espn_bot.espn_bot` builds the existing text exactly as today and, for tabular reports, also builds Slack blocks, routing blocks to Slack and text to the other platforms.

**Tech Stack:** Python 3.11, `dataclasses`, `requests`, `pytest`, `requests_mock` (already in `requirements-test.txt`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-11-slack-table-formatting-design.md`

## Global Constraints

- GroupMe and Discord text output must not change. The existing 171 tests pin it; they must stay green after every task.
- Every table cell is a non-empty string. Slack rejects `""` with `invalid_blocks`. Cells with nothing to show use `"-"`.
- All table cells are `{"type": "raw_text", "text": ...}`. No `raw_number`.
- Table limits: 100 rows, 20 columns. The renderer raises `ValueError` beyond these; no splitting.
- Team names in tables are the full `team_name`, formatted `"{team_name} ({wins}-{losses})"` where a record is shown.
- Scores and projections are formatted `"%.2f"`.
- Run tests from the repo root with the project venv active: `pytest -q`. Working directory matters because tests do `sys.path.insert(1, os.path.abspath('.'))`.
- Every commit message ends with the line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Work on branch `slack-tables` (already exists, contains the spec).

## File structure

| File | Responsibility |
|---|---|
| `gamedaybot/espn/tables.py` (create) | `Table` dataclass and the six structured builders. Pure data shaping; reuses helpers from `functionality.py`. |
| `gamedaybot/espn/functionality.py` (modify) | Two extractions only: `close_matchups(box_scores, threshold)` and `power_ranking_rows(league, week)`, each used by the existing text builder and the new table builder. |
| `gamedaybot/chat/slack_format.py` (create) | `table_blocks(table)` and `text_blocks(text)`: pure functions producing Block Kit dicts. |
| `gamedaybot/chat/slack.py` (modify) | `send_blocks(blocks, fallback)`; `send_message` delegates to it. |
| `gamedaybot/espn/espn_bot.py` (modify) | Build `slack_blocks` for tabular reports; route sends. |
| `tests/test_tables.py` (create) | Builders against fake league objects. |
| `tests/test_slack_format.py` (create) | Renderer output. |
| `tests/test_slack.py` (modify) | Client posts blocks and fallback. |
| `tests/test_espn_bot_routing.py` (create) | Send routing with the network stubbed out. |

Import convention: `functionality.py` imports `gamedaybot.utils.util as util` inside an `if os.environ.get("AWS_EXECUTION_ENV")` guard. New modules follow the same guard so the Lambda layout keeps working.

---

### Task 1: `Table` dataclass and `matchups_table`

**Files:**
- Create: `gamedaybot/espn/tables.py`
- Create: `tests/test_tables.py`

**Interfaces:**
- Produces: `Table(title: str, headers: list[str], rows: list[list[str]], align: list[str])`; `matchups_table(league, week=None, box_scores=None) -> Table | None`; test fakes `FakeTeam`, `FakePlayer`, `FakeBox` in `tests/test_tables.py` reused by later tasks.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tables.py`:

```python
import sys
import os
sys.path.insert(1, os.path.abspath('.'))

import gamedaybot.espn.tables as tables
from gamedaybot.espn.tables import Table


class FakePlayer:
    """One lineup slot. Defaults to a starter who has not played yet."""

    def __init__(self, projected_points=10.0, points=0.0, game_played=0, slot_position='WR'):
        self.projected_points = projected_points
        self.points = points
        self.game_played = game_played
        self.slot_position = slot_position


class FakeTeam:
    def __init__(self, name, abbrev, wins=0, losses=0, playoff_pct=0.0):
        self.team_name = name
        self.team_abbrev = abbrev
        self.wins = wins
        self.losses = losses
        self.playoff_pct = playoff_pct


class FakeBox:
    """Stands in for an espn_api BoxScore.

    Projections come from a single lineup player each side; scores are the
    BoxScore's own home_score / away_score. away_team=None models a bye.
    """

    def __init__(self, home, away, home_proj=100.0, away_proj=90.0,
                 home_score=0.0, away_score=0.0, played=False):
        self.home_team = home
        self.away_team = away
        self.home_score = home_score
        self.away_score = away_score
        gp = 100 if played else 0
        self.home_lineup = [FakePlayer(projected_points=home_proj, game_played=gp,
                                       points=home_proj if played else 0.0)]
        self.away_lineup = [FakePlayer(projected_points=away_proj, game_played=gp,
                                       points=away_proj if played else 0.0)]


HOME = FakeTeam('The Rising Cost of Living', 'BigK', wins=2, losses=1)
AWAY = FakeTeam('Studio Gibbsli', 'CAM', wins=1, losses=2)


class TestMatchupsTable:
    def test_title_and_columns(self):
        t = tables.matchups_table(None, box_scores=[FakeBox(HOME, AWAY)])
        assert t.title == 'Matchups'
        assert t.headers == ['Home', 'Proj', 'Away', 'Proj']
        assert t.align == ['left', 'right', 'left', 'right']

    def test_row_uses_full_names_with_records_and_projections(self):
        t = tables.matchups_table(None, box_scores=[FakeBox(HOME, AWAY, home_proj=102.434, away_proj=93.76)])
        assert t.rows == [['The Rising Cost of Living (2-1)', '102.43', 'Studio Gibbsli (1-2)', '93.76']]

    def test_bye_boxes_are_skipped(self):
        boxes = [FakeBox(HOME, None), FakeBox(HOME, AWAY)]
        assert len(tables.matchups_table(None, box_scores=boxes).rows) == 1

    def test_returns_none_when_every_box_is_a_bye(self):
        assert tables.matchups_table(None, box_scores=[FakeBox(HOME, None)]) is None

    def test_returns_none_for_empty_week(self):
        assert tables.matchups_table(None, box_scores=[]) is None

    def test_no_cell_is_empty(self):
        t = tables.matchups_table(None, box_scores=[FakeBox(FakeTeam('', ''), AWAY)])
        assert all(cell for row in t.rows for cell in row)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_tables.py`
Expected: `ModuleNotFoundError: No module named 'gamedaybot.espn.tables'`

- [ ] **Step 3: Implement `Table` and `matchups_table`**

Create `gamedaybot/espn/tables.py`:

```python
"""Structured (row/column) versions of the bot's tabular reports.

The text builders in functionality.py return preformatted strings for chat
platforms that only render monospace text. Slack can render real tables, so
these builders return a Table that gamedaybot.chat.slack_format turns into
Block Kit blocks. They return None exactly when the matching text builder
would return its "nothing to send" sentinel.
"""
import os
from dataclasses import dataclass
from typing import List, Optional

if os.environ.get("AWS_EXECUTION_ENV") is not None:
    import espn.functionality as espn
else:
    import sys
    sys.path.insert(1, os.path.abspath('.'))
    import gamedaybot.espn.functionality as espn

LEFT, RIGHT, CENTER = 'left', 'right', 'center'

# Slack rejects empty table cells, so this stands in for "nothing here".
EMPTY_CELL = '-'


@dataclass
class Table:
    title: str
    headers: List[str]
    rows: List[List[str]]
    align: List[str]


def _cell(value) -> str:
    text = str(value)
    return text if text else EMPTY_CELL


def _score(value) -> str:
    return '%.2f' % value


def _team(team) -> str:
    return _cell(f"{team.team_name} ({team.wins}-{team.losses})")


def _played_boxes(league, week, box_scores):
    if box_scores is None:
        box_scores = espn.fetch_box_scores(league, week=week)
    return [box for box in box_scores if box.away_team]


def matchups_table(league, week=None, box_scores=None) -> Optional[Table]:
    played = _played_boxes(league, week, box_scores)
    if not played:
        return None
    rows = [[_team(box.home_team), _score(espn.get_projected_total(box.home_lineup)),
             _team(box.away_team), _score(espn.get_projected_total(box.away_lineup))]
            for box in played]
    return Table('Matchups', ['Home', 'Proj', 'Away', 'Proj'], rows, [LEFT, RIGHT, LEFT, RIGHT])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_tables.py`
Expected: 6 passed

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all pass (171 existing + 6)

- [ ] **Step 6: Commit**

```bash
git add gamedaybot/espn/tables.py tests/test_tables.py
git commit -m "Add Table value object and matchups_table builder

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `scoreboard_table` and `projected_table`

**Files:**
- Modify: `gamedaybot/espn/tables.py`
- Modify: `tests/test_tables.py`

**Interfaces:**
- Consumes: `Table`, `_team`, `_score`, `_played_boxes` from Task 1; fakes from `tests/test_tables.py`.
- Produces: `scoreboard_table(league, week=None, box_scores=None, title='Score Update', projected=True) -> Table | None`; `projected_table(league, week=None, box_scores=None) -> Table | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tables.py`:

```python
class TestScoreboardTable:
    def test_default_title_and_columns_include_projections(self):
        t = tables.scoreboard_table(None, box_scores=[FakeBox(HOME, AWAY)])
        assert t.title == 'Score Update'
        assert t.headers == ['Home', 'Score', 'Proj', 'Away', 'Score', 'Proj']
        assert t.align == ['left', 'right', 'right', 'left', 'right', 'right']

    def test_row_has_scores_and_projections(self):
        box = FakeBox(HOME, AWAY, home_proj=110.0, away_proj=95.5, home_score=54.2, away_score=61.0)
        t = tables.scoreboard_table(None, box_scores=[box])
        assert t.rows == [['The Rising Cost of Living (2-1)', '54.20', '110.00',
                           'Studio Gibbsli (1-2)', '61.00', '95.50']]

    def test_projected_false_drops_proj_columns(self):
        box = FakeBox(HOME, AWAY, home_score=54.2, away_score=61.0)
        t = tables.scoreboard_table(None, box_scores=[box], title='Final Score Update', projected=False)
        assert t.title == 'Final Score Update'
        assert t.headers == ['Home', 'Score', 'Away', 'Score']
        assert t.align == ['left', 'right', 'left', 'right']
        assert t.rows == [['The Rising Cost of Living (2-1)', '54.20', 'Studio Gibbsli (1-2)', '61.00']]

    def test_returns_none_when_no_matchups(self):
        assert tables.scoreboard_table(None, box_scores=[FakeBox(HOME, None)]) is None


class TestProjectedTable:
    def test_title_columns_and_row(self):
        t = tables.projected_table(None, box_scores=[FakeBox(HOME, AWAY, home_proj=102.43, away_proj=93.76)])
        assert t.title == 'Approximate Projected Scores'
        assert t.headers == ['Home', 'Proj', 'Away', 'Proj']
        assert t.align == ['left', 'right', 'left', 'right']
        assert t.rows == [['The Rising Cost of Living (2-1)', '102.43', 'Studio Gibbsli (1-2)', '93.76']]

    def test_returns_none_when_no_matchups(self):
        assert tables.projected_table(None, box_scores=[]) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_tables.py`
Expected: 6 failures with `AttributeError: module 'gamedaybot.espn.tables' has no attribute 'scoreboard_table'` (and `projected_table`)

- [ ] **Step 3: Implement**

Append to `gamedaybot/espn/tables.py`:

```python
def scoreboard_table(league, week=None, box_scores=None, title='Score Update',
                     projected=True) -> Optional[Table]:
    played = _played_boxes(league, week, box_scores)
    if not played:
        return None
    rows = []
    for box in played:
        home = [_team(box.home_team), _score(box.home_score)]
        away = [_team(box.away_team), _score(box.away_score)]
        if projected:
            home.append(_score(espn.get_projected_total(box.home_lineup)))
            away.append(_score(espn.get_projected_total(box.away_lineup)))
        rows.append(home + away)
    if projected:
        headers = ['Home', 'Score', 'Proj', 'Away', 'Score', 'Proj']
        align = [LEFT, RIGHT, RIGHT, LEFT, RIGHT, RIGHT]
    else:
        headers = ['Home', 'Score', 'Away', 'Score']
        align = [LEFT, RIGHT, LEFT, RIGHT]
    return Table(title, headers, rows, align)


def projected_table(league, week=None, box_scores=None) -> Optional[Table]:
    played = _played_boxes(league, week, box_scores)
    if not played:
        return None
    rows = [[_team(box.home_team), _score(espn.get_projected_total(box.home_lineup)),
             _team(box.away_team), _score(espn.get_projected_total(box.away_lineup))]
            for box in played]
    return Table('Approximate Projected Scores', ['Home', 'Proj', 'Away', 'Proj'], rows,
                 [LEFT, RIGHT, LEFT, RIGHT])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_tables.py`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add gamedaybot/espn/tables.py tests/test_tables.py
git commit -m "Add scoreboard_table and projected_table builders

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Extract `close_matchups` helper and add `close_scores_table`

**Files:**
- Modify: `gamedaybot/espn/functionality.py:369-416` (`get_close_scores`)
- Modify: `gamedaybot/espn/tables.py`
- Modify: `tests/test_tables.py`

**Interfaces:**
- Produces: `functionality.close_matchups(box_scores, threshold) -> list[tuple[box, float, float]]` (box, home_projected, away_projected); `tables.close_scores_table(league, week=None, box_scores=None, threshold=espn.CLOSE_SCORES_DEFAULT_THRESHOLD) -> Table | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tables.py`:

```python
import gamedaybot.espn.functionality as espn


class TestCloseMatchupsHelper:
    def test_returns_box_with_projections_inside_threshold(self):
        box = FakeBox(HOME, AWAY, home_proj=100.0, away_proj=110.0)
        assert espn.close_matchups([box], 15) == [(box, 100.0, 110.0)]

    def test_excludes_outside_threshold(self):
        assert espn.close_matchups([FakeBox(HOME, AWAY, home_proj=100.0, away_proj=130.0)], 15) == []

    def test_excludes_completed_games(self):
        assert espn.close_matchups([FakeBox(HOME, AWAY, home_proj=100.0, away_proj=101.0, played=True)], 15) == []

    def test_excludes_byes(self):
        assert espn.close_matchups([FakeBox(HOME, None)], 15) == []


class TestCloseScoresTable:
    def test_title_columns_and_row(self):
        t = tables.close_scores_table(None, box_scores=[FakeBox(HOME, AWAY, home_proj=100.0, away_proj=105.5)])
        assert t.title == 'Projected Close Scores'
        assert t.headers == ['Home', 'Proj', 'Away', 'Proj']
        assert t.align == ['left', 'right', 'left', 'right']
        assert t.rows == [['The Rising Cost of Living (2-1)', '100.00', 'Studio Gibbsli (1-2)', '105.50']]

    def test_threshold_is_respected(self):
        boxes = [FakeBox(HOME, AWAY, home_proj=100.0, away_proj=130.0)]
        assert tables.close_scores_table(None, box_scores=boxes) is None
        assert tables.close_scores_table(None, box_scores=boxes, threshold=40) is not None

    def test_matches_text_builder_selection(self):
        boxes = [
            FakeBox(FakeTeam('Close', 'CLS'), FakeTeam('Opp', 'OPP'), home_proj=100.0, away_proj=105.0),
            FakeBox(FakeTeam('Far', 'FAR'), FakeTeam('Away', 'AWY'), home_proj=100.0, away_proj=150.0),
        ]
        text = espn.get_close_scores(None, box_scores=boxes)
        table = tables.close_scores_table(None, box_scores=boxes)
        assert len(text.splitlines()) - 1 == len(table.rows) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_tables.py`
Expected: failures with `AttributeError: module 'gamedaybot.espn.functionality' has no attribute 'close_matchups'` and `... 'tables' has no attribute 'close_scores_table'`

- [ ] **Step 3: Extract the helper in `functionality.py`**

Insert immediately before `def get_close_scores(` (around line 369):

```python
def close_matchups(box_scores, threshold):
    """
    Select the matchups whose projected margin is within the threshold and
    which still have players left to play.

    Returns a list of (box_score, home_projected, away_projected) tuples, in
    box-score order. Both the text and table close-score reports build from
    this so they can never disagree about which matchups are "close".
    """
    close = []
    for i in box_scores:
        if not i.away_team:
            continue
        away_projected = get_projected_total(i.away_lineup)
        home_projected = get_projected_total(i.home_lineup)
        # The lineup-derived projections are used for both the margin test and
        # the report, so the printed gap always agrees with the threshold that
        # selected the matchup. i.home_projected / i.away_projected are the
        # BoxScore's own totals, which aggregate across a 2-week playoff matchup.
        if (abs(away_projected - home_projected) <= threshold
                and (not all_played(i.away_lineup) or not all_played(i.home_lineup))):
            close.append((i, home_projected, away_projected))
    return close
```

Then replace the body of `get_close_scores` after its docstring (from `# Gets current projected closest scores` through `return '\n'.join(text)`) with:

```python
    # Gets current projected closest scores (within the threshold)
    if box_scores is None:
        box_scores = fetch_box_scores(league, week=week)
    score = ['%4s %6.2f - %6.2f %s' % (i.home_team.team_abbrev, home_projected,
                                       away_projected, i.away_team.team_abbrev)
             for i, home_projected, away_projected in close_matchups(box_scores, threshold)]
    if not score:
        return ('')
    text = ['Projected Close Scores'] + score
    return '\n'.join(text)
```

- [ ] **Step 4: Add the table builder**

Append to `gamedaybot/espn/tables.py`:

```python
def close_scores_table(league, week=None, box_scores=None,
                       threshold=espn.CLOSE_SCORES_DEFAULT_THRESHOLD) -> Optional[Table]:
    if box_scores is None:
        box_scores = espn.fetch_box_scores(league, week=week)
    close = espn.close_matchups(box_scores, threshold)
    if not close:
        return None
    rows = [[_team(box.home_team), _score(home_projected), _team(box.away_team), _score(away_projected)]
            for box, home_projected, away_projected in close]
    return Table('Projected Close Scores', ['Home', 'Proj', 'Away', 'Proj'], rows,
                 [LEFT, RIGHT, LEFT, RIGHT])
```

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all pass. `tests/test_functionality.py::TestGetCloseScores` (11 tests) proves the text output survived the extraction.

- [ ] **Step 6: Commit**

```bash
git add gamedaybot/espn/functionality.py gamedaybot/espn/tables.py tests/test_tables.py
git commit -m "Share close-matchup selection between text and table reports

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `standings_table`

**Files:**
- Modify: `gamedaybot/espn/tables.py`
- Modify: `tests/test_tables.py`

**Interfaces:**
- Produces: `standings_table(league) -> Table`. Calls `league.standings()` which returns teams in rank order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tables.py`:

```python
class FakeStandingsLeague:
    def __init__(self, teams):
        self._teams = teams

    def standings(self):
        return self._teams


class TestStandingsTable:
    def test_title_columns_and_rows_in_rank_order(self):
        league = FakeStandingsLeague([FakeTeam('First', 'ONE', wins=3, losses=0),
                                      FakeTeam('Second', 'TWO', wins=2, losses=1)])
        t = tables.standings_table(league)
        assert t.title == 'Current Standings'
        assert t.headers == ['Rank', 'Record', 'Team']
        assert t.align == ['right', 'center', 'left']
        assert t.rows == [['1', '3-0', 'First'], ['2', '2-1', 'Second']]

    def test_empty_team_name_is_not_an_empty_cell(self):
        t = tables.standings_table(FakeStandingsLeague([FakeTeam('', 'X')]))
        assert t.rows[0][2] == '-'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_tables.py -k Standings`
Expected: `AttributeError: module 'gamedaybot.espn.tables' has no attribute 'standings_table'`

- [ ] **Step 3: Implement**

Append to `gamedaybot/espn/tables.py`:

```python
def standings_table(league) -> Table:
    rows = [[str(pos), f"{team.wins}-{team.losses}", _cell(team.team_name)]
            for pos, team in enumerate(league.standings(), start=1)]
    return Table('Current Standings', ['Rank', 'Record', 'Team'], rows, [RIGHT, CENTER, LEFT])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_tables.py`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add gamedaybot/espn/tables.py tests/test_tables.py
git commit -m "Add standings_table builder

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Extract `power_ranking_rows` helper and add `power_rankings_table`

**Files:**
- Modify: `gamedaybot/espn/functionality.py:624-689` (`get_power_rankings`)
- Modify: `gamedaybot/espn/tables.py`
- Modify: `tests/test_tables.py`

**Interfaces:**
- Produces: `functionality.power_ranking_rows(league, week=None) -> list[tuple[team, str, float | None]]` (team, normalized score string like `"99.99"`, change percent or `None` when there is no previous week); `functionality.rank_change_emoji(change_percent) -> str`; `tables.power_rankings_table(league, week=None) -> Table`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tables.py`:

```python
class FakePowerLeague:
    """power_rankings(week) returns [(score_str, team), ...] like espn_api."""

    def __init__(self, by_week, current_week=3):
        self._by_week = by_week
        self.current_week = current_week

    def power_rankings(self, week):
        return self._by_week.get(week, [])


UP = FakeTeam('Climber', 'UP', playoff_pct=80.0)
DOWN = FakeTeam('Faller', 'DN', playoff_pct=20.5)


class TestPowerRankingRowsHelper:
    def test_normalizes_top_score_to_99_99(self):
        league = FakePowerLeague({2: [('50.0', UP), ('25.0', DOWN)]})
        rows = espn.power_ranking_rows(league, week=2)
        assert [(t.team_abbrev, s) for t, s, _ in rows] == [('UP', '99.99'), ('DN', '50.00')]

    def test_change_is_none_on_first_week(self):
        league = FakePowerLeague({1: [('50.0', UP)]})
        assert espn.power_ranking_rows(league, week=1)[0][2] is None

    def test_change_percent_against_previous_week(self):
        league = FakePowerLeague({1: [('50.0', UP), ('50.0', DOWN)],
                                  2: [('50.0', UP), ('25.0', DOWN)]})
        rows = espn.power_ranking_rows(league, week=2)
        assert rows[0][2] == 0.0
        assert round(rows[1][2], 1) == -50.0

    def test_defaults_to_week_before_current(self):
        league = FakePowerLeague({2: [('50.0', UP)]}, current_week=3)
        assert len(espn.power_ranking_rows(league)) == 1

    def test_text_report_still_matches_helper(self):
        league = FakePowerLeague({1: [('50.0', UP), ('50.0', DOWN)],
                                  2: [('50.0', UP), ('25.0', DOWN)]})
        text = espn.get_power_rankings(league, week=2)
        assert text.splitlines() == ['Power Rankings (Playoff %)',
                                     '99.99[🟰 0.0%] (80.0) - UP',
                                     '50.00[🔻50.0%] (20.5) - DN']


class TestPowerRankingsTable:
    def test_title_columns_and_rows(self):
        league = FakePowerLeague({1: [('50.0', UP), ('50.0', DOWN)],
                                  2: [('50.0', UP), ('25.0', DOWN)]})
        t = tables.power_rankings_table(league, week=2)
        assert t.title == 'Power Rankings'
        assert t.headers == ['Rank', 'Team', 'Score', 'Change', 'Playoff %']
        assert t.align == ['right', 'left', 'right', 'right', 'right']
        assert t.rows == [['1', 'Climber', '99.99', '🟰0.0%', '80.0'],
                          ['2', 'Faller', '50.00', '🔻50.0%', '20.5']]

    def test_first_week_change_is_dash(self):
        t = tables.power_rankings_table(FakePowerLeague({1: [('50.0', UP)]}), week=1)
        assert t.rows[0][3] == '-'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_tables.py -k Power`
Expected: `AttributeError: ... has no attribute 'power_ranking_rows'` and `'power_rankings_table'`

- [ ] **Step 3: Extract the helper in `functionality.py`**

Insert immediately before `def get_power_rankings(`:

```python
P_RANK_UP_EMOJI = "🟢"
P_RANK_DOWN_EMOJI = "🔻"
P_RANK_SAME_EMOJI = "🟰"


def rank_change_emoji(change_percent):
    if change_percent > 0:
        return P_RANK_UP_EMOJI
    if change_percent < 0:
        return P_RANK_DOWN_EMOJI
    return P_RANK_SAME_EMOJI


def power_ranking_rows(league, week=None):
    """
    Compute the power rankings for a week with each team's change from the
    week before.

    Returns a list of (team, normalized_score, change_percent) in ranking
    order. normalized_score is a string with two decimals, scaled so the top
    team is "99.99". change_percent is a float, or None when there is no
    previous week to compare against. Both the text and table power ranking
    reports build from this.
    """
    if not week:
        week = league.current_week - 1

    current_rankings = league.power_rankings(week=week)
    previous_rankings = league.power_rankings(week=week - 1) if week > 1 else []

    def normalize_rankings(rankings):
        if not rankings:
            return []
        max_score = max(float(score) for score, _ in rankings)
        return [(f"{99.99 * float(score) / max_score:.2f}", team) for score, team in rankings]

    normalized_current = normalize_rankings(current_rankings)
    previous_by_abbrev = {team.team_abbrev: score for score, team in normalize_rankings(previous_rankings)}

    rows = []
    for score, team in normalized_current:
        change = None
        if team.team_abbrev in previous_by_abbrev:
            previous = float(previous_by_abbrev[team.team_abbrev])
            change = ((float(score) - previous) / previous) * 100
        rows.append((team, score, change))
    return rows
```

Then replace the body of `get_power_rankings` after its docstring (from `# Check if the week is provided` through `return '\n'.join(rankings_text)`) with:

```python
    rows = power_ranking_rows(league, week=week)

    # Scores are padded to a common width so the columns after them stay
    # aligned when a team's score drops below 10.
    rankings_text = ['Power Rankings (Playoff %)']
    aligned_scores = util.align_scores([score for _, score, _ in rows])
    for (team, _, change), score_text in zip(rows, aligned_scores):
        rank_change_text = ''
        if change is not None:
            rank_change_text = f"[{rank_change_emoji(change)}{abs(change):4.1f}%]"
        rankings_text.append(f"{score_text}{rank_change_text} ({team.playoff_pct:4.1f}) - {team.team_abbrev}")
    return '\n'.join(rankings_text)
```

- [ ] **Step 4: Add the table builder**

Append to `gamedaybot/espn/tables.py`:

```python
def power_rankings_table(league, week=None) -> Table:
    rows = []
    for rank, (team, score, change) in enumerate(espn.power_ranking_rows(league, week=week), start=1):
        change_cell = EMPTY_CELL if change is None else f"{espn.rank_change_emoji(change)}{abs(change):.1f}%"
        rows.append([str(rank), _cell(team.team_name), score, change_cell, f"{team.playoff_pct:.1f}"])
    return Table('Power Rankings', ['Rank', 'Team', 'Score', 'Change', 'Playoff %'], rows,
                 [RIGHT, LEFT, RIGHT, RIGHT, RIGHT])
```

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all pass, including `test_text_report_still_matches_helper`, which pins the text format through the extraction.

- [ ] **Step 6: Commit**

```bash
git add gamedaybot/espn/functionality.py gamedaybot/espn/tables.py tests/test_tables.py
git commit -m "Share power ranking computation between text and table reports

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `slack_format.table_blocks`

**Files:**
- Create: `gamedaybot/chat/slack_format.py`
- Create: `tests/test_slack_format.py`

**Interfaces:**
- Consumes: `Table` from `gamedaybot.espn.tables`.
- Produces: `table_blocks(table: Table) -> list[dict]` (a `section` block then a `table` block); `escape(text: str) -> str`; constants `MAX_TABLE_ROWS = 100`, `MAX_TABLE_COLUMNS = 20`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_slack_format.py`:

```python
import sys
import os
import pytest
sys.path.insert(1, os.path.abspath('.'))

from gamedaybot.espn.tables import Table
import gamedaybot.chat.slack_format as fmt


def sample_table():
    return Table('Matchups', ['Home', 'Proj', 'Away', 'Proj'],
                 [['A (1-0)', '100.00', 'B (0-1)', '90.00']],
                 ['left', 'right', 'left', 'right'])


class TestEscape:
    def test_escapes_slack_control_characters(self):
        assert fmt.escape('A & B <C> D') == 'A &amp; B &lt;C&gt; D'


class TestTableBlocks:
    def test_returns_title_section_then_table(self):
        blocks = fmt.table_blocks(sample_table())
        assert [b['type'] for b in blocks] == ['section', 'table']
        assert blocks[0]['text'] == {'type': 'mrkdwn', 'text': '*Matchups*'}

    def test_title_is_escaped(self):
        t = sample_table()
        t.title = 'Tom & Jerry'
        assert fmt.table_blocks(t)[0]['text']['text'] == '*Tom &amp; Jerry*'

    def test_header_row_comes_first_and_cells_are_raw_text(self):
        table = fmt.table_blocks(sample_table())[1]
        assert table['rows'][0] == [{'type': 'raw_text', 'text': h} for h in ['Home', 'Proj', 'Away', 'Proj']]
        assert table['rows'][1] == [{'type': 'raw_text', 'text': c} for c in ['A (1-0)', '100.00', 'B (0-1)', '90.00']]

    def test_column_settings_map_alignment_and_wrap_left_columns(self):
        table = fmt.table_blocks(sample_table())[1]
        assert table['column_settings'] == [
            {'align': 'left', 'is_wrapped': True},
            {'align': 'right'},
            {'align': 'left', 'is_wrapped': True},
            {'align': 'right'},
        ]

    def test_empty_cells_become_dash(self):
        t = sample_table()
        t.rows = [['', '1.00', 'B', '2.00']]
        assert fmt.table_blocks(t)[1]['rows'][1][0]['text'] == '-'

    def test_too_many_rows_raises(self):
        t = sample_table()
        t.rows = [['A', '1', 'B', '2']] * fmt.MAX_TABLE_ROWS  # plus the header row exceeds the limit
        with pytest.raises(ValueError):
            fmt.table_blocks(t)

    def test_too_many_columns_raises(self):
        n = fmt.MAX_TABLE_COLUMNS + 1
        t = Table('Wide', ['h'] * n, [['c'] * n], ['left'] * n)
        with pytest.raises(ValueError):
            fmt.table_blocks(t)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_slack_format.py`
Expected: `ModuleNotFoundError: No module named 'gamedaybot.chat.slack_format'`

- [ ] **Step 3: Implement**

Create `gamedaybot/chat/slack_format.py`:

```python
"""Render bot reports as Slack Block Kit blocks.

Pure functions: no network, no environment. Slack's table block was probed
against a live incoming webhook on 2026-09-11; see
docs/superpowers/specs/2026-09-11-slack-table-formatting-design.md for what
it accepts (raw_text cells only, no empty cells, 100 rows, 20 columns).
"""

MAX_TABLE_ROWS = 100      # including the header row
MAX_TABLE_COLUMNS = 20
EMPTY_CELL = '-'


def escape(text):
    """Escape the three characters Slack treats as control characters in text."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _title_section(title):
    return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*{escape(title)}*'}}


def _raw_text(cell):
    return {'type': 'raw_text', 'text': cell if cell else EMPTY_CELL}


def table_blocks(table):
    """A bold title section followed by a table block for the given Table."""
    rows = [table.headers] + table.rows
    if len(rows) > MAX_TABLE_ROWS:
        raise ValueError(f"Slack tables allow {MAX_TABLE_ROWS} rows including the header; got {len(rows)}")
    if len(table.headers) > MAX_TABLE_COLUMNS:
        raise ValueError(f"Slack tables allow {MAX_TABLE_COLUMNS} columns; got {len(table.headers)}")

    column_settings = []
    for align in table.align:
        setting = {'align': align}
        if align == 'left':
            setting['is_wrapped'] = True
        column_settings.append(setting)

    return [
        _title_section(table.title),
        {
            'type': 'table',
            'column_settings': column_settings,
            'rows': [[_raw_text(cell) for cell in row] for row in rows],
        },
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_slack_format.py`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add gamedaybot/chat/slack_format.py tests/test_slack_format.py
git commit -m "Add Slack Block Kit table renderer

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `slack_format.text_blocks`

**Files:**
- Modify: `gamedaybot/chat/slack_format.py`
- Modify: `tests/test_slack_format.py`

**Interfaces:**
- Produces: `text_blocks(text: str) -> list[dict]` of `section` blocks; constant `SECTION_BODY_LIMIT = 2900`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_slack_format.py`:

```python
class TestTextBlocks:
    def test_single_line_is_plain_section_without_code_block(self):
        assert fmt.text_blocks('bot is back online') == [
            {'type': 'section', 'text': {'type': 'mrkdwn', 'text': 'bot is back online'}}]

    def test_single_line_is_escaped(self):
        assert fmt.text_blocks('a < b')[0]['text']['text'] == 'a &lt; b'

    def test_multiline_bolds_first_line_and_code_blocks_the_rest(self):
        blocks = fmt.text_blocks('Waiver Report 2026-09-10:\nTEAM\nADDED Player A\nDROPPED Player B')
        assert blocks == [{'type': 'section', 'text': {
            'type': 'mrkdwn',
            'text': '*Waiver Report 2026-09-10:*\n```\nTEAM\nADDED Player A\nDROPPED Player B\n```'}}]

    def test_body_is_escaped_inside_code_block(self):
        text = fmt.text_blocks('Title\nA & B')[0]['text']['text']
        assert 'A &amp; B' in text

    def test_long_body_splits_across_sections_at_line_boundaries(self):
        lines = [f'line {i:04d} ' + 'x' * 90 for i in range(60)]  # ~6000 chars
        blocks = fmt.text_blocks('Title\n' + '\n'.join(lines))
        assert len(blocks) >= 2
        assert blocks[0]['text']['text'].startswith('*Title*\n```\n')
        for block in blocks:
            assert len(block['text']['text']) <= 3000
            body = block['text']['text'].split('```')[1]
            assert all(line.startswith('line ') for line in body.strip('\n').split('\n'))
        joined = '\n'.join(b['text']['text'].split('```')[1].strip('\n') for b in blocks)
        assert joined.split('\n') == lines
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_slack_format.py -k TextBlocks`
Expected: `AttributeError: module 'gamedaybot.chat.slack_format' has no attribute 'text_blocks'`

- [ ] **Step 3: Implement**

Append to `gamedaybot/chat/slack_format.py`:

```python
# Slack caps a section's text at 3000 characters. Code-block bodies are split
# below this so the fence characters and title fit alongside them.
SECTION_BODY_LIMIT = 2900


def _section(text):
    return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}


def _chunk_lines(lines, limit):
    """Group lines into chunks whose joined length stays within limit."""
    chunks, current, size = [], [], 0
    for line in lines:
        if current and size + len(line) + 1 > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append(current)
    return chunks


def text_blocks(text):
    """Render a text report: a lone line as plain text, otherwise a bold title
    over a code block that preserves the report's column alignment."""
    lines = escape(text).split('\n')
    if len(lines) == 1:
        return [_section(lines[0])]
    title, body = lines[0], lines[1:]
    blocks = []
    for index, chunk in enumerate(_chunk_lines(body, SECTION_BODY_LIMIT)):
        code = '```\n' + '\n'.join(chunk) + '\n```'
        blocks.append(_section(f'*{title}*\n{code}' if index == 0 else code))
    return blocks
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q tests/test_slack_format.py`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add gamedaybot/chat/slack_format.py tests/test_slack_format.py
git commit -m "Render Slack text reports with bold titles and code blocks

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: `Slack.send_blocks`, and `send_message` delegates to it

**Files:**
- Modify: `gamedaybot/chat/slack.py:1-72`
- Modify: `tests/test_slack.py`

**Interfaces:**
- Consumes: `text_blocks` from Task 7.
- Produces: `Slack.send_blocks(blocks: list[dict], fallback: str) -> requests.Response | None`; `Slack.send_message(text: str)` unchanged signature, now posts `{"text": text, "blocks": text_blocks(text)}`.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/test_slack.py` with:

```python
import pytest
import sys
import os
sys.path.insert(1, os.path.abspath('.'))
from gamedaybot.chat.slack import (Slack, SlackException, )


@pytest.mark.usefixtures("mock_requests")
class TestSlack:
    '''Test SlackBot class'''

    def setup_method(self):
        self.url = "https://hooks.slack.com/services/A1B2C3/ABC1ABC2/abcABC1abcABC2"
        self.test_bot = Slack(self.url)
        self.test_text = "This is a test."

    def test_send_message(self, mock_requests):
        '''Does the message send successfully?'''
        mock_requests.post(self.url, status_code=200)
        assert self.test_bot.send_message(self.test_text).status_code == 200

    def test_send_message_posts_blocks_with_plain_fallback(self, mock_requests):
        mock_requests.post(self.url, status_code=200)
        self.test_bot.send_message("Title\nrow one")
        body = mock_requests.last_request.json()
        assert body["text"] == "Title\nrow one"
        assert body["blocks"] == [{"type": "section", "text": {
            "type": "mrkdwn", "text": "*Title*\n```\nrow one\n```"}}]

    def test_send_blocks_posts_given_blocks_and_fallback(self, mock_requests):
        mock_requests.post(self.url, status_code=200)
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*Hi*"}}]
        assert self.test_bot.send_blocks(blocks, fallback="Hi").status_code == 200
        assert mock_requests.last_request.json() == {"text": "Hi", "blocks": blocks}

    def test_send_blocks_raises_on_error(self, mock_requests):
        mock_requests.post(self.url, status_code=400, text="invalid_blocks")
        with pytest.raises(SlackException):
            self.test_bot.send_blocks([], fallback="x")

    def test_unset_webhook_sends_nothing(self, mock_requests):
        for unset in (1, "1", ""):
            assert Slack(unset).send_blocks([], fallback="x") is None
            assert Slack(unset).send_message("x") is None
        assert mock_requests.call_count == 0

    def test_bad_bot_id(self, mock_requests):
        '''Does the expected error raise when a bot id is incorrect?'''
        mock_requests.post(self.url, status_code=404)
        with pytest.raises(SlackException):
            self.test_bot.send_message(self.test_text)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_slack.py`
Expected: `test_send_message_posts_blocks_with_plain_fallback` fails on `KeyError: 'blocks'`; the `send_blocks` tests fail with `AttributeError: 'Slack' object has no attribute 'send_blocks'`.

- [ ] **Step 3: Implement**

Replace `gamedaybot/chat/slack.py` from the `import` lines through the end of `send_message` with:

```python
import requests
import json
import logging
import os

if os.environ.get("AWS_EXECUTION_ENV") is not None:
    from chat.slack_format import text_blocks
else:
    import sys
    sys.path.insert(1, os.path.abspath('.'))
    from gamedaybot.chat.slack_format import text_blocks

logger = logging.getLogger(__name__)


class SlackException(Exception):
    pass


class Slack:
    """
    Send messages to a Slack channel through an incoming webhook.

    Parameters
    ----------
    webhook_url : str
        The URL of the Slack webhook to send messages to. 1, "1" or "" means
        Slack is not configured and sends are silently skipped.
    """

    UNSET = (1, "1", "")

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def __repr__(self):
        return "Slack Webhook Url(%s)" % self.webhook_url

    def send_blocks(self, blocks, fallback: str):
        """
        Post Block Kit blocks to the channel.

        Parameters
        ----------
        blocks : list of dict
            Block Kit blocks, e.g. from gamedaybot.chat.slack_format.
        fallback : str
            Plain text Slack shows in notifications and clients that cannot
            render blocks.

        Returns
        -------
        requests.Response, or None when the webhook is not configured.

        Raises
        ------
        SlackException
            If Slack returns anything other than 200.
        """
        if self.webhook_url in self.UNSET:
            return None

        payload = {"text": fallback, "blocks": blocks}
        headers = {'content-type': 'application/json'}
        r = requests.post(self.webhook_url, data=json.dumps(payload), headers=headers)

        if r.status_code != 200:
            logger.error(r.content)
            raise SlackException(r.content)

        return r

    def send_message(self, text: str):
        """
        Send a text report. Multi-line reports get a bold first line over a
        code block; a single line is sent as plain text.
        """
        return self.send_blocks(text_blocks(text), fallback=text)
```

- [ ] **Step 4: Run the whole suite**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add gamedaybot/chat/slack.py tests/test_slack.py
git commit -m "Post Slack messages as Block Kit blocks with a text fallback

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Route tables to Slack in `espn_bot`

**Files:**
- Modify: `gamedaybot/espn/espn_bot.py:1-25` (imports), `:156-222` (dispatch and send)
- Create: `tests/test_espn_bot_routing.py`

**Interfaces:**
- Consumes: all six builders from `gamedaybot.espn.tables`; `table_blocks`, `text_blocks` from `gamedaybot.chat.slack_format`; `Slack.send_blocks`.
- Produces: no new public interface. `espn_bot(function)` behaviour: Slack gets blocks for tabular reports, text otherwise; GroupMe and Discord unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/test_espn_bot_routing.py`:

```python
"""espn_bot send routing, with ESPN and the chat platforms stubbed out.

espn_bot() reads its config from the environment and builds a League from
espn_api, so the League class and all three chat clients are replaced with
recorders. The functionality/table builders are replaced too: these tests are
about which platform receives what, not about report content.
"""
import sys
import os
import pytest
sys.path.insert(1, os.path.abspath('.'))

import gamedaybot.espn.espn_bot as bot_module
from gamedaybot.espn.tables import Table


class Recorder:
    def __init__(self, *args, **kwargs):
        self.messages = []
        self.blocks = []

    def send_message(self, text):
        self.messages.append(text)

    def send_blocks(self, blocks, fallback):
        self.blocks.append((blocks, fallback))


class FakeLeague:
    def __init__(self, *args, **kwargs):
        self.scoringPeriodId = 3
        self.firstScoringPeriod = 1
        self.finalScoringPeriod = 17
        self.current_week = 3


SAMPLE_TABLE = Table('Matchups', ['Home', 'Proj', 'Away', 'Proj'],
                     [['A (1-0)', '100.00', 'B (0-1)', '90.00']], ['left', 'right', 'left', 'right'])


@pytest.fixture
def bots(monkeypatch):
    monkeypatch.setenv('LEAGUE_ID', '1234567')
    monkeypatch.setenv('BOT_ID', 'x' * 20)
    monkeypatch.setenv('SLACK_WEBHOOK_URL', 'https://hooks.slack.com/services/A/B/C')
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/1/x')
    recorders = {}

    def make(name):
        def factory(*args, **kwargs):
            recorders[name] = Recorder()
            return recorders[name]
        return factory

    monkeypatch.setattr(bot_module, 'GroupMe', make('groupme'))
    monkeypatch.setattr(bot_module, 'Slack', make('slack'))
    monkeypatch.setattr(bot_module, 'Discord', make('discord'))
    monkeypatch.setattr(bot_module, 'League', FakeLeague)
    return recorders


def test_matchups_sends_text_to_groupme_discord_and_table_to_slack(bots, monkeypatch):
    monkeypatch.setattr(bot_module.espn, 'fetch_box_scores', lambda league, week=None: ['box'])
    monkeypatch.setattr(bot_module.espn, 'get_matchups', lambda league, **kw: 'Matchups\nA vs B')
    monkeypatch.setattr(bot_module.espn, 'get_projected_scoreboard', lambda league, **kw: 'Approximate Projected Scores\nA 100.00 - 90.00 B')
    monkeypatch.setattr(bot_module.tables, 'matchups_table', lambda league, **kw: SAMPLE_TABLE)

    bot_module.espn_bot('get_matchups')

    expected_text = 'Matchups\nA vs B\n\nApproximate Projected Scores\nA 100.00 - 90.00 B'
    assert bots['groupme'].messages == [expected_text]
    assert bots['discord'].messages == [expected_text]
    assert bots['slack'].messages == []
    (blocks, fallback), = bots['slack'].blocks
    assert fallback == expected_text
    assert [b['type'] for b in blocks] == ['section', 'table']


def test_text_only_report_goes_to_slack_as_text(bots, monkeypatch):
    monkeypatch.setattr(bot_module.espn, 'get_monitor', lambda league: 'Starting Players to Monitor\nQB Someone - Questionable')

    bot_module.espn_bot('get_monitor')

    assert bots['slack'].messages == ['Starting Players to Monitor\nQB Someone - Questionable']
    assert bots['slack'].blocks == []


def test_final_sends_score_table_and_trophies_text_in_one_slack_message(bots, monkeypatch):
    monkeypatch.setattr(bot_module.espn, 'fetch_box_scores', lambda league, week=None: ['box'])
    monkeypatch.setattr(bot_module.espn, 'get_scoreboard_short', lambda league, **kw: 'Score Update\nA 100.00 - 90.00 B')
    monkeypatch.setattr(bot_module.espn, 'get_trophies', lambda league, **kw: 'Trophies of the week:\n👑 High score 👑\nA with 100.00 points')
    captured = {}

    def fake_scoreboard_table(league, **kw):
        captured.update(kw)
        return Table('Final Score Update', ['Home', 'Score', 'Away', 'Score'],
                     [['A (1-0)', '100.00', 'B (0-1)', '90.00']], ['left', 'right', 'left', 'right'])
    monkeypatch.setattr(bot_module.tables, 'scoreboard_table', fake_scoreboard_table)

    bot_module.espn_bot('get_final')

    assert captured['title'] == 'Final Score Update'
    assert captured['projected'] is False
    assert captured['week'] == 2
    (blocks, fallback), = bots['slack'].blocks
    assert [b['type'] for b in blocks] == ['section', 'table', 'section']
    assert blocks[2]['text']['text'].startswith('*Trophies of the week:*\n```')
    assert bots['groupme'].messages == ['Final Score Update\nA 100.00 - 90.00 B\n\nTrophies of the week:\n👑 High score 👑\nA with 100.00 points']


def test_nothing_sent_when_report_is_sentinel(bots, monkeypatch):
    monkeypatch.setattr(bot_module.espn, 'fetch_box_scores', lambda league, week=None: [])
    monkeypatch.setattr(bot_module.espn, 'get_matchups', lambda league, **kw: bot_module.util.NO_MATCHUP_DATA)
    monkeypatch.setattr(bot_module.tables, 'matchups_table', lambda league, **kw: None)

    bot_module.espn_bot('get_matchups')

    assert bots['slack'].blocks == [] and bots['slack'].messages == []
    assert bots['groupme'].messages == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -q tests/test_espn_bot_routing.py`
Expected: `AttributeError: module 'gamedaybot.espn.espn_bot' has no attribute 'tables'`

- [ ] **Step 3: Add the imports**

In `gamedaybot/espn/espn_bot.py`, in the `AWS_EXECUTION_ENV` branch add after `from chat.discord import Discord`:

```python
    import espn.tables as tables
    from chat.slack_format import table_blocks, text_blocks
```

and in the local branch add after `import gamedaybot.espn.season_recap as recap`:

```python
    import gamedaybot.espn.tables as tables
    from gamedaybot.chat.slack_format import table_blocks, text_blocks
```

- [ ] **Step 4: Build Slack blocks in the dispatch**

In `espn_bot()`, immediately before `text = ''` (the line above `logger.info("Function: " + function)`), add:

```python
    slack_blocks = None
```

Then replace the dispatch branches listed below. Every other branch is unchanged.

```python
    if function == "get_matchups":
        box_scores = espn.fetch_box_scores(league)
        text = espn.get_matchups(league, box_scores=box_scores)
        if text != util.NO_MATCHUP_DATA:
            text = text + "\n\n" + espn.get_projected_scoreboard(league, box_scores=box_scores)
        table = tables.matchups_table(league, box_scores=box_scores)
        if table:
            slack_blocks = table_blocks(table)
    elif function == "get_monitor":
        text = espn.get_monitor(league)
    elif function == "get_scoreboard_short":
        box_scores = espn.fetch_box_scores(league)
        text = espn.get_scoreboard_short(league, box_scores=box_scores)
        if text != util.NO_MATCHUP_DATA:
            text = text + "\n\n" + espn.get_projected_scoreboard(league, box_scores=box_scores)
        table = tables.scoreboard_table(league, box_scores=box_scores)
        if table:
            slack_blocks = table_blocks(table)
    elif function == "get_projected_scoreboard":
        box_scores = espn.fetch_box_scores(league)
        text = espn.get_projected_scoreboard(league, box_scores=box_scores)
        table = tables.projected_table(league, box_scores=box_scores)
        if table:
            slack_blocks = table_blocks(table)
    elif function == "get_close_scores":
        box_scores = espn.fetch_box_scores(league)
        text = espn.get_close_scores(league, box_scores=box_scores, threshold=close_scores_threshold)
        table = tables.close_scores_table(league, box_scores=box_scores, threshold=close_scores_threshold)
        if table:
            slack_blocks = table_blocks(table)
    elif function == "get_power_rankings":
        text = espn.get_power_rankings(league)
        slack_blocks = table_blocks(tables.power_rankings_table(league))
    elif function == "get_trophies":
        text = espn.get_trophies(league)
    elif function == "get_standings":
        text = espn.get_standings(league)
        slack_blocks = table_blocks(tables.standings_table(league))
```

and the `get_final` branch:

```python
    elif function == "get_final":
        # on Tuesday we need to get the scores of last week
        week = league.current_week - 1
        box_scores = espn.fetch_box_scores(league, week=week)
        scores = espn.get_scoreboard_short(league, week=week, box_scores=box_scores)
        if scores == util.NO_MATCHUP_DATA:
            text = scores
        else:
            trophies = espn.get_trophies(league, week=week, box_scores=box_scores)
            text = "Final " + scores
            text = text + "\n\n" + trophies
            table = tables.scoreboard_table(league, week=week, box_scores=box_scores,
                                            title="Final Score Update", projected=False)
            if table:
                slack_blocks = table_blocks(table) + text_blocks(trophies)
```

Note `get_projected_scoreboard` and `get_close_scores` previously let the text builder fetch box scores itself. Fetching once and passing `box_scores` to both builders avoids a second ESPN call and guarantees text and table describe the same data.

- [ ] **Step 5: Route the sends**

Replace the send loop at the end of `espn_bot()`:

```python
    logger.debug(data)
    if util.has_sendable_content(text):
        logger.debug(text)
        messages = util.str_limit_check(text, str_limit)
        for message in messages:
            groupme_bot.send_message(message)
            discord_bot.send_message(message)
        if slack_blocks:
            slack_bot.send_blocks(slack_blocks, fallback=text)
        else:
            for message in messages:
                slack_bot.send_message(message)
```

- [ ] **Step 6: Run the whole suite**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add gamedaybot/espn/espn_bot.py tests/test_espn_bot_routing.py
git commit -m "Send tabular reports to Slack as native tables

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Live verification and pull request

**Files:**
- None modified. Uses `war-cardinola-bot.env` (git-ignored, contains real credentials; never print its contents or commit it).

- [ ] **Step 1: Send the matchups report to the real channel**

From the repo root with the venv active:

```bash
set -a; source war-cardinola-bot.env; set +a
python -c "from gamedaybot.espn.espn_bot import espn_bot; espn_bot('get_matchups')"
```

Expected: exits without a traceback. In Slack, the channel shows a bold "Matchups" line over a rendered table with Home, Proj, Away, Proj columns and full team names with records. Nothing else is posted to Slack for this report.

- [ ] **Step 2: Send one text-only report to check the bold-title path**

```bash
python -c "from gamedaybot.espn.espn_bot import espn_bot; espn_bot('get_standings')"
```

Expected: a "Current Standings" table with Rank, Record, Team columns. (This is a second table check; standings is the report with no ESPN box-score dependency, so it always has rows.)

- [ ] **Step 3: Confirm the working tree is clean and push**

```bash
git status --short
git push -u origin slack-tables
```

Expected: `git status` shows only the untracked env file is ignored (no output). Push succeeds.

- [ ] **Step 4: Open the pull request**

```bash
gh pr create --base master --head slack-tables --title "Send Slack reports as native tables" --body "$(cat <<'EOF'
## What

Slack now receives the tabular reports (matchups, score update, projected scores, close scores, standings, power rankings, and the Tuesday final) as Block Kit table blocks with a bold title, and every other report with a bold title over a code block. GroupMe and Discord output is unchanged.

Spec: `docs/superpowers/specs/2026-09-11-slack-table-formatting-design.md`

## How

- `gamedaybot/espn/tables.py`: structured `Table` builders for the six reports.
- `gamedaybot/chat/slack_format.py`: pure renderers `table_blocks` and `text_blocks`.
- `gamedaybot/chat/slack.py`: `send_blocks(blocks, fallback)`; `send_message` now posts blocks with a plain-text fallback.
- `gamedaybot/espn/espn_bot.py`: builds blocks alongside the existing text and routes blocks to Slack only.
- `functionality.py`: close-score selection and power-ranking computation extracted into helpers shared by the text and table builders, so the two can never disagree. Existing tests pin the text output.

## Verification

- New tests: `tests/test_tables.py`, `tests/test_slack_format.py`, `tests/test_espn_bot_routing.py`, plus extended `tests/test_slack.py`. Each written first and watched fail.
- Full suite passes.
- Sent the matchups and standings reports to the live channel; both rendered as tables.

## Notes

Slack's table block was probed against the live incoming webhook: it works, but rejects empty cells and the undocumented `raw_number` cell type, so all cells are `raw_text` with right-aligned numeric columns.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: a PR URL is printed and `gh pr view --json mergeable` reports `MERGEABLE`.
