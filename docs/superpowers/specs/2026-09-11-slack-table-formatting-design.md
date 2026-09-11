# Slack table formatting

**Date:** 2026-09-11
**Status:** approved in discussion, pending spec review

## Goal

Slack messages from the bot should use Slack's native table block for the
tabular reports, and bold titles for everything else, instead of one grey
code block. GroupMe and Discord output must not change.

## Verified constraints (probed against the live webhook on 2026-09-11)

- Incoming webhooks accept Block Kit `table` blocks. Slack's docs only mention
  `chat.postMessage`, but the webhook returned 200 and the table rendered.
- `column_settings` with `align` and `is_wrapped` are accepted.
- A cell with an empty string is rejected with `invalid_blocks`. Every cell
  must contain at least one character.
- `raw_number` cells have an undocumented schema and were rejected. All cells
  are `raw_text`; numeric columns are right-aligned via `column_settings`.
- Hard limits from the docs: 100 rows and 20 columns per table, 10,000
  characters across all cells in a message. A fantasy league's reports are far
  below these, so the code does not split tables. The renderer raises a
  `ValueError` if a table exceeds the row or column limit so the failure is
  loud rather than a silent `invalid_blocks`.

## Architecture

Three layers, each testable on its own:

```
functionality.py / tables.py          slack_format.py              slack.py
(league data -> Table or str)  -->   (Table|str -> blocks)  -->   (blocks -> webhook POST)
                                                                  
espn_bot.py decides, per report, which builders to call and routes:
  text   -> GroupMe, Discord (unchanged)
  blocks -> Slack
```

### 1. `Table` value object and structured builders

New module `gamedaybot/espn/tables.py`.

```python
@dataclass
class Table:
    title: str
    headers: list[str]
    rows: list[list[str]]
    align: list[str]      # one of "left" | "right" | "center" per column
```

All cell values are strings. Builders never emit an empty string; a cell with
nothing to show uses `"-"`.

Team names in tables are the full `team_name` (cells wrap), not the
abbreviation the text reports use for width reasons.

Builders return `None` when the corresponding text builder would return its
"nothing to send" sentinel, so `espn_bot` can apply the same skip logic.

| Builder | Title | Columns (alignment) | Rows | Returns `None` when |
|---|---|---|---|---|
| `matchups_table(league, week=None, box_scores=None)` | `Matchups` | Home (left, wrapped), Proj (right), Away (left, wrapped), Proj (right) | one per box score with an away team; team cell is `"{team_name} ({wins}-{losses})"`; Proj is `get_projected_total` of the lineup, `%.2f` | no box score has an away team |
| `scoreboard_table(league, week=None, box_scores=None, title="Score Update", projected=True)` | given title | Home, Score (right), Proj (right), Away, Score (right), Proj (right); the two Proj columns are omitted when `projected=False` | one per box score with an away team; scores `%.2f` | no box score has an away team |
| `projected_table(league, week=None, box_scores=None)` | `Approximate Projected Scores` | Home, Proj (right), Away, Proj (right) | as above | no box score has an away team |
| `close_scores_table(league, week=None, box_scores=None, threshold=...)` | `Projected Close Scores` | Home, Proj (right), Away, Proj (right) | same selection rule as `get_close_scores` | no matchup is within the threshold |
| `standings_table(league)` | `Current Standings` | Rank (right), Record (center), Team (left, wrapped) | one per team from `league.standings()` | never |
| `power_rankings_table(league, week=None)` | `Power Rankings` | Rank (right), Team (left, wrapped), Score (right), Change (right), Playoff % (right) | one per team; Change is `"{emoji}{pct:.1f}%"` or `"-"` for the first ranked week | never |

`get_power_rankings` currently computes normalized scores and week-over-week
change inline. That computation is extracted into a private helper in
`functionality.py` returning `(team, normalized_score, change_percent_or_None)`
tuples, used by both the text builder and `power_rankings_table`. The text
output is unchanged, which the existing tests verify. The other tabular text
builders are one-line list comprehensions over box scores and are not
refactored; the table builders repeat that one line.

`get_close_scores` selection logic (threshold and `all_played` check) is
likewise extracted into a private helper returning the matching box scores
with their projections, shared by both builders, so the two can never
disagree about which matchups are "close".

### 2. Slack block rendering

New module `gamedaybot/chat/slack_format.py`, pure functions, no I/O.

`table_blocks(table: Table) -> list[dict]` returns two blocks:

1. A `section` block with `mrkdwn` text `*{title}*` (title escaped for
   `&`, `<`, `>`).
2. A `table` block: `column_settings` from `table.align`, with
   `is_wrapped: true` on left-aligned columns; `rows` is the header row
   followed by data rows, every cell `{"type": "raw_text", "text": ...}`.
   Any empty cell string is replaced by `"-"` as a last line of defence.
   Raises `ValueError` when rows exceed 100 or columns exceed 20.

`text_blocks(text: str) -> list[dict]` renders a text report:

- Single line: one `section` block with the escaped text as `mrkdwn`, no
  code block. (Init and broadcast messages.)
- Multiple lines: the first line becomes `*title*`, the remaining lines go in
  a fenced code block, in one `section` block. Column alignment in the text
  reports is preserved.

Section text is limited to 3,000 characters by Slack. `text_blocks` splits
the code-block body across multiple `section` blocks at line boundaries when
the body exceeds 2,900 characters, so long waiver reports still send.

### 3. Slack client

`gamedaybot/chat/slack.py`:

- `send_message(text)` is unchanged in signature. Its body becomes
  `send_blocks(text_blocks(text), fallback=text)` so every text message to
  Slack gets the bold-title treatment.
- New `send_blocks(blocks: list[dict], fallback: str)` posts
  `{"text": fallback, "blocks": blocks}`. `fallback` is the plain text Slack
  shows in notifications. Existing behaviour is kept: skip when the webhook
  URL is unset (`1`, `"1"`, `""`), log and raise `SlackException` on a
  non-200 response.

### 4. Bot send path

`gamedaybot/espn/espn_bot.py` currently builds a single `text`. It will build
`text` exactly as today and, for the reports below, also `slack_blocks`.

| Function | `slack_blocks` |
|---|---|
| `get_matchups` | `table_blocks(matchups_table(...))` |
| `get_scoreboard_short` | `table_blocks(scoreboard_table(...))` (one table, scores and projections together) |
| `get_projected_scoreboard` | `table_blocks(projected_table(...))` |
| `get_close_scores` | `table_blocks(close_scores_table(...))` |
| `get_standings` | `table_blocks(standings_table(...))` |
| `get_power_rankings` | `table_blocks(power_rankings_table(...))` |
| `get_final` | `table_blocks(scoreboard_table(..., title="Final Score Update", projected=False))` + `text_blocks(trophies)` (projections are meaningless after the games are played) |
| everything else | not set |

Sending:

```python
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

The `has_sendable_content(text)` gate stays as the single decision for
whether anything is sent; `slack_blocks` is only built when a table builder
returned a `Table`, and a `None` table means `text` is the sentinel anyway.

## Error handling

- A `None` from a table builder is not an error; it mirrors the text sentinel.
- `table_blocks` raising `ValueError` on oversize tables surfaces in the
  scheduler job log like any other exception; GroupMe and Discord sends happen
  first, so a Slack rendering problem never blocks the other platforms.
- Slack `invalid_blocks` still raises `SlackException` with the response body.

## Testing

- `tests/test_tables.py`: each builder against fake league/box score objects
  in the style of `tests/test_functionality.py`. Covers: row contents and
  formatting, `None` on empty data, no empty cells, power ranking change
  column on first week and later weeks, close-score threshold selection
  matching `get_close_scores`.
- `tests/test_slack_format.py`: `table_blocks` structure, header row first,
  alignment mapping, `"-"` substitution, oversize `ValueError`, escaping;
  `text_blocks` single-line vs multi-line, long-body splitting.
- `tests/test_slack.py`: `send_blocks` posts the expected JSON body (via
  `requests_mock`), `send_message` now sends blocks plus fallback, existing
  error and skip behaviour preserved.
- `tests/test_functionality.py`: existing tests pin `get_power_rankings` and
  `get_close_scores` text through the helper extraction.
- Manual: send the matchups report to the real channel via the env file and
  confirm it renders as a table.

## Out of scope

- GroupMe and Discord formatting.
- Splitting tables that exceed Slack's limits.
- Restructuring the text reports or `functionality.py` beyond the two helper
  extractions above.
- Season recap functions (`win_matrix`, `trophy_recap`), which stay text.
