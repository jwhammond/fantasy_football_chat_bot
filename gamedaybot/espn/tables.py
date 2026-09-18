"""Structured versions of the bot's reports.

The text builders in functionality.py return preformatted strings for chat
platforms that only render monospace text. Slack can render real tables, so
these builders return a Table that gamedaybot.chat.slack_format turns into
Block Kit blocks. A report whose rows are not really columnar returns a
LabeledList instead, rendered as bold labels over their values. Both return
None exactly when the matching text builder would return its "nothing to
send" sentinel.
"""
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

if os.environ.get("AWS_EXECUTION_ENV") is not None:
    import espn.functionality as espn
    import espn.season_recap as recap
else:
    import sys
    sys.path.insert(1, os.path.abspath('.'))
    import gamedaybot.espn.functionality as espn
    import gamedaybot.espn.season_recap as recap

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


@dataclass
class LabeledList:
    """A titled run of label/value pairs, for reports that are not tables.

    The trophies read as a list of awards, not as rows: every value is a
    sentence of its own length ("171.30 points" beside "left 27.10 points on
    their bench..."), so a third table column would wrap badly. Rendered by
    gamedaybot.chat.slack_format.list_blocks as bold labels over their values.
    """
    title: str
    items: List[Tuple[str, str]]


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


def monitor_table(league, box_scores=None) -> Optional[Table]:
    """
    Build the starters worth watching as a Table of team, player, and status.

    Shares monitor_roster with the text builder, so the two can never disagree
    about who is flagged or why.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the table for.
    box_scores : list, optional
        Pre-fetched box scores for the current week, to avoid a duplicate API call.

    Returns
    -------
    Table or None
        None when no starter is flagged -- the case where the text builder
        reports "No Players to Monitor this week".
    """
    if box_scores is None:
        box_scores = espn.fetch_box_scores(league)

    rows = []
    for box in box_scores:
        # A bye leaves away_team None; its lineup flags nobody, but reading
        # team_name off it would still crash.
        for team, lineup in ((box.home_team, box.home_lineup), (box.away_team, box.away_lineup)):
            if team is None:
                continue
            for player, reason in espn.monitor_roster(lineup):
                rows.append([_cell(team.team_name), _cell(player), _cell(reason)])

    if not rows:
        return None
    return Table('Starting Players to Monitor', ['Team', 'Player', 'Status'], rows,
                 [LEFT, LEFT, LEFT])


def trophies_list(league, week=None, box_scores=None) -> Optional[LabeledList]:
    """
    Build the week's trophies as a LabeledList of award labels and winners.

    Shares trophy_pairs with the text builder, so the two can never disagree
    about which trophies were won.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the list for.
    week : int, optional
        The week to award for. Defaults to the week before the current week.
    box_scores : list, optional
        Pre-fetched box scores for the same week, to avoid a duplicate API call.

    Returns
    -------
    LabeledList or None
        None for a week with nothing played -- the case where the text builder
        returns its NO_TROPHY_DATA sentinel.
    """
    pairs = espn.trophy_pairs(league, week=week, box_scores=box_scores)
    if not pairs:
        return None
    return LabeledList(espn.TROPHY_TITLE, pairs)


def waiver_table(league, faab=False, scoring_period=None, test_date=None) -> Optional[Table]:
    """
    Build the day's executed waiver claims as a Table, one row per move.

    Shares waiver_moves with the text builder, so the two can never disagree
    about which claims are reported or in what order. The FAAB column is
    omitted entirely in a league that does not use FAAB.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the table for.
    faab : bool, optional
        If True, include the FAAB column and sort by FAAB descending.
    scoring_period : int, optional
        The scoring period to query. Defaults to league.scoringPeriodId.
    test_date : str, optional
        Date string (YYYY-MM-DD) to simulate 'today'. Defaults to today.

    Returns
    -------
    Table or None
        None when no claim was executed on the report date -- the case where
        the text builder returns ''.
    """
    today, entries = espn.waiver_moves(league, faab=faab, scoring_period=scoring_period,
                                       test_date=test_date)
    if not entries:
        return None

    rows = []
    for team_name, moves in entries:
        for action, position, player, detail in moves:
            row = [_cell(team_name), action, _cell(position), _cell(player)]
            if faab:
                # Only an add carries a bid; a drop's cell would otherwise be empty.
                row.append(_cell(detail))
            rows.append(row)

    headers = ['Team', 'Move', 'Pos', 'Player']
    align = [LEFT, LEFT, LEFT, LEFT]
    if faab:
        headers.append('FAAB')
        align.append(LEFT)
    return Table(f'Waiver Report {today}', headers, rows, align)


def win_matrix_table(league) -> Optional[Table]:
    """
    Build the everyone-played-everyone standings as a Table.

    Shares win_matrix_records with the text builder, so the two can never
    disagree about the ordering.

    Parameters
    ----------
    league : espn_api.football.League
        The league to build the table for.

    Returns
    -------
    Table or None
        None for a league with no teams.
    """
    records = recap.win_matrix_records(league)
    if not records:
        return None
    rows = [[str(rank), _cell(abbrev), f'{wins}-{losses}']
            for rank, (abbrev, wins, losses) in enumerate(records, start=1)]
    return Table(recap.WIN_MATRIX_TITLE, ['Rank', 'Team', 'Record'], rows,
                 [RIGHT, LEFT, RIGHT])
