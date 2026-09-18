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
# Intentionally duplicated in chat/slack_format.py: chat/ must not import
# espn/, so the two modules cannot share this constant.
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
    """
    Build the current week's matchups as a Table of home/away teams and projections.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the table for.
    week : int, optional
        The week to build for. Defaults to the league's current week.
    box_scores : list, optional
        Pre-fetched box scores for the same week, to avoid a duplicate API call.

    Returns
    -------
    Table or None
        None when no box score has an away team (bye week or no data).
    """
    played = _played_boxes(league, week, box_scores)
    if not played:
        return None
    rows = _projection_rows(played)
    return Table('Matchups', ['Home', 'Proj', 'Away', 'Proj'], rows, [LEFT, RIGHT, LEFT, RIGHT])


def scoreboard_table(league, week=None, box_scores=None, title='Score Update',
                     projected=True) -> Optional[Table]:
    """
    Build a scoreboard Table of home/away teams, scores, and optional projections.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the table for.
    week : int, optional
        The week to build for. Defaults to the league's current week.
    box_scores : list, optional
        Pre-fetched box scores for the same week, to avoid a duplicate API call.
    title : str, optional
        The table title. Defaults to "Score Update"; callers pass e.g.
        "Final Score Update" for a completed week.
    projected : bool, optional
        Whether to include the Proj columns. False for a final report, where
        projections are meaningless after the games are played.

    Returns
    -------
    Table or None
        None when no box score has an away team (bye week or no data).
    """
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
    """
    Build a Table of projected scores for the remaining games in a week.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the table for.
    week : int, optional
        The week to build for. Defaults to the league's current week.
    box_scores : list, optional
        Pre-fetched box scores for the same week, to avoid a duplicate API call.

    Returns
    -------
    Table or None
        None when no box score has an away team (bye week or no data).
    """
    played = _played_boxes(league, week, box_scores)
    if not played:
        return None
    rows = _projection_rows(played)
    return Table('Approximate Projected Scores', ['Home', 'Proj', 'Away', 'Proj'], rows,
                 [LEFT, RIGHT, LEFT, RIGHT])


def close_scores_table(league, week=None, box_scores=None,
                       threshold=espn.CLOSE_SCORES_DEFAULT_THRESHOLD) -> Optional[Table]:
    """
    Build a Table of matchups whose projected point difference is within a threshold.

    Uses the same close_matchups selection helper as the text builder, so the
    two can never disagree about which matchups are "close".

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the table for.
    week : int, optional
        The week to build for. Defaults to the league's current week.
    box_scores : list, optional
        Pre-fetched box scores for the same week, to avoid a duplicate API call.
    threshold : float, optional
        The largest projected point difference that still counts as close.
        Defaults to CLOSE_SCORES_DEFAULT_THRESHOLD.

    Returns
    -------
    Table or None
        None when no matchup is within the threshold.
    """
    if box_scores is None:
        box_scores = espn.fetch_box_scores(league, week=week)
    close = espn.close_matchups(box_scores, threshold)
    if not close:
        return None
    rows = [[_team(box.home_team), _score(home_projected), _team(box.away_team), _score(away_projected)]
            for box, home_projected, away_projected in close]
    return Table('Projected Close Scores', ['Home', 'Proj', 'Away', 'Proj'], rows,
                 [LEFT, RIGHT, LEFT, RIGHT])


def standings_tables(league) -> List[Table]:
    """
    Build the current league standings as one Table per division.

    Shares division_standings with the text builder, so the two can never
    disagree about grouping, ranks, or which teams hold a playoff spot. The
    playoff marker rides on the team cell rather than a column of its own,
    which would leave every non-playoff row filled with EMPTY_CELL.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the tables for.

    Returns
    -------
    list of Table
        One Table per division, ranked within the division, in the order the
        divisions appear in the standings. A league without divisions gets a
        single unmarked Table titled 'Current Standings'. Never empty.
    """
    return [Table(f"Current Standings - {division_name}" if division_name else 'Current Standings',
                  ['Rank', 'Record', 'Team'],
                  [[str(pos), f"{team.wins}-{team.losses}", _marked_team(team, marker)]
                   for pos, team, marker in rows],
                  [RIGHT, CENTER, LEFT])
            for division_name, rows in espn.division_standings(league)]


def _marked_team(team, marker) -> str:
    """The team's name with its playoff marker, if it holds a playoff spot.

    Names are stripped first: ESPN hands back some with trailing whitespace,
    which would otherwise double up the space in front of the marker.
    """
    name = _cell(team.team_name.strip())
    return f"{name} {marker}" if marker else name


def power_rankings_table(league, week=None) -> Table:
    """
    Build the power rankings as a Table of rank, team, normalized score, and week-over-week change.

    Uses the same power_ranking_rows helper as the text builder, so the two
    can never disagree about scores, ranks, or change percentages.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the table for.
    week : int, optional
        The week to rank. Defaults to the week before the league's current week.

    Returns
    -------
    Table
        One row per team, ranked highest score first. Never returns None; the
        Change column is "-" for the first ranked week.
    """
    rows = []
    for rank, (team, score, change) in enumerate(espn.power_ranking_rows(league, week=week), start=1):
        change_cell = EMPTY_CELL if change is None else f"{espn.rank_change_emoji(change)}{abs(change):.1f}%"
        rows.append([str(rank), _cell(team.team_name), score, change_cell, f"{team.playoff_pct:.1f}"])
    return Table('Power Rankings', ['Rank', 'Team', 'Score', 'Change', 'Playoff %'], rows,
                 [RIGHT, LEFT, RIGHT, RIGHT, RIGHT])
