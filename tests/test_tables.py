import sys
import os
sys.path.insert(1, os.path.abspath('.'))

import gamedaybot.espn.tables as tables
import gamedaybot.espn.functionality as espn
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

    def test_cell_substitutes_dash_for_empty_and_passes_through_otherwise(self):
        assert tables._cell('') == '-'
        assert tables._cell('x') == 'x'


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
        assert [(t.team_abbrev, s) for t, s, _ in rows] == [('UP', '99.99'), ('DN', '49.99')]

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
                                     '49.99[🔻50.0%] (20.5) - DN']


class TestPowerRankingsTable:
    def test_title_columns_and_rows(self):
        league = FakePowerLeague({1: [('50.0', UP), ('50.0', DOWN)],
                                  2: [('50.0', UP), ('25.0', DOWN)]})
        t = tables.power_rankings_table(league, week=2)
        assert t.title == 'Power Rankings'
        assert t.headers == ['Rank', 'Team', 'Score', 'Change', 'Playoff %']
        assert t.align == ['right', 'left', 'right', 'right', 'right']
        assert t.rows == [['1', 'Climber', '99.99', '🟰0.0%', '80.0'],
                          ['2', 'Faller', '49.99', '🔻50.0%', '20.5']]

    def test_first_week_change_is_dash(self):
        t = tables.power_rankings_table(FakePowerLeague({1: [('50.0', UP)]}), week=1)
        assert t.rows[0][3] == '-'
