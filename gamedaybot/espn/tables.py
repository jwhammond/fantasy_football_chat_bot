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


def _projection_rows(played):
    """Build rows of [home team, home proj, away team, away proj] for a list of played boxes."""
    return [[_team(box.home_team), _score(espn.get_projected_total(box.home_lineup)),
             _team(box.away_team), _score(espn.get_projected_total(box.away_lineup))]
            for box in played]


def matchups_table(league, week=None, box_scores=None) -> Optional[Table]:
    played = _played_boxes(league, week, box_scores)
    if not played:
        return None
    rows = _projection_rows(played)
    return Table('Matchups', ['Home', 'Proj', 'Away', 'Proj'], rows, [LEFT, RIGHT, LEFT, RIGHT])


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
    rows = _projection_rows(played)
    return Table('Approximate Projected Scores', ['Home', 'Proj', 'Away', 'Proj'], rows,
                 [LEFT, RIGHT, LEFT, RIGHT])
