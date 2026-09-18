"""Tests for the season recap reports."""
import sys
import os
from types import SimpleNamespace
sys.path.insert(1, os.path.abspath('.'))

import gamedaybot.espn.season_recap as recap


def league_with(records_by_week, teams):
    """A league stub whose weekly results are supplied directly.

    records_by_week maps a week to the ordered list of team stubs, best score
    first -- the shape get_weekly_score_with_win_loss returns.
    """
    league = SimpleNamespace(teams=teams, current_week=len(records_by_week) + 1)
    return league


class FakeTeam:
    """Hashable team stub: get_weekly_score_with_win_loss keys its dict by team."""

    def __init__(self, abbrev):
        self.team_abbrev = abbrev


def team(abbrev):
    return FakeTeam(abbrev)


class TestWinMatrixRecords:
    def test_undefeated_team_does_not_crash_the_sort(self, monkeypatch):
        # A team that outscores everyone every week has zero losses, which the
        # old wins/losses sort key divided by.
        teams = [team('AAA'), team('BBB'), team('CCC')]
        monkeypatch.setattr(recap.espn, 'get_weekly_score_with_win_loss',
                            lambda league, week: {t: [0, 'W'] for t in teams})

        records = recap.win_matrix_records(league_with({1: teams}, teams))

        assert records == [('AAA', 2, 0), ('BBB', 1, 1), ('CCC', 0, 2)]

    def test_orders_by_win_percentage(self, monkeypatch):
        teams = [team('AAA'), team('BBB'), team('CCC')]
        order = {1: [teams[2], teams[0], teams[1]]}
        monkeypatch.setattr(recap.espn, 'get_weekly_score_with_win_loss',
                            lambda league, week: {t: [0, 'W'] for t in order[week]})

        records = recap.win_matrix_records(league_with(order, teams))

        assert [abbrev for abbrev, _, _ in records] == ['CCC', 'AAA', 'BBB']

    def test_before_any_week_is_played_every_record_is_zero(self, monkeypatch):
        teams = [team('AAA'), team('BBB')]
        league = SimpleNamespace(teams=teams, current_week=1)
        monkeypatch.setattr(recap.espn, 'get_weekly_score_with_win_loss',
                            lambda league, week: {})

        assert recap.win_matrix_records(league) == [('AAA', 0, 0), ('BBB', 0, 0)]


class TestWinMatrix:
    def test_renders_ranked_lines(self, monkeypatch):
        monkeypatch.setattr(recap, 'win_matrix_records',
                            lambda league: [('AAA', 9, 2), ('BBB', 4, 7)])

        text = recap.win_matrix(None)

        assert text.split('\n') == [recap.WIN_MATRIX_TITLE,
                                    ' 1. AAA  (9-2)',
                                    ' 2. BBB  (4-7)']
