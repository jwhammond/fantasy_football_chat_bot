import sys
import os
from types import SimpleNamespace
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
    def __init__(self, name, abbrev, wins=0, losses=0, playoff_pct=0.0,
                 division_id=0, division_name=''):
        self.team_name = name
        self.team_abbrev = abbrev
        self.wins = wins
        self.losses = losses
        self.playoff_pct = playoff_pct
        self.division_id = division_id
        self.division_name = division_name


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
    def __init__(self, teams, playoff_team_count=4):
        self._teams = teams
        self.settings = SimpleNamespace(playoff_team_count=playoff_team_count)

    def standings(self):
        return self._teams


def two_division_league():
    """Four teams, seeds 1-4, alternating East/West, 4 playoff spots."""
    return FakeStandingsLeague([
        FakeTeam('Alpha', 'ALP', wins=3, losses=0, division_id=1, division_name='East'),
        FakeTeam('Bravo', 'BRV', wins=3, losses=0, division_id=2, division_name='West'),
        FakeTeam('Charlie', 'CHR', wins=2, losses=1, division_id=1, division_name='East'),
        FakeTeam('Delta', 'DLT', wins=1, losses=2, division_id=2, division_name='West'),
    ])


class TestStandingsTables:
    def test_one_table_per_division_titled_with_its_name(self):
        assert [t.title for t in tables.standings_tables(two_division_league())] == [
            'Current Standings - East', 'Current Standings - West']

    def test_columns_are_unchanged(self):
        east = tables.standings_tables(two_division_league())[0]
        assert east.headers == ['Rank', 'Record', 'Team']
        assert east.align == ['right', 'center', 'left']

    def test_rank_restarts_at_one_in_each_division(self):
        west = tables.standings_tables(two_division_league())[1]
        assert [row[0] for row in west.rows] == ['1', '2']

    def test_playoff_marker_is_appended_to_the_team_cell(self):
        east, west = tables.standings_tables(two_division_league())
        assert east.rows == [['1', '3-0', f'Alpha {espn.DIVISION_LEADER}'],
                             ['2', '2-1', f'Charlie {espn.WILD_CARD}']]
        assert west.rows[0] == ['1', '3-0', f'Bravo {espn.DIVISION_LEADER}']

    def test_team_outside_the_playoff_field_has_a_bare_name(self):
        league = FakeStandingsLeague(two_division_league()._teams, playoff_team_count=2)
        assert tables.standings_tables(league)[0].rows[1] == ['2', '2-1', 'Charlie']

    def test_league_without_divisions_is_one_untitled_table(self):
        league = FakeStandingsLeague([FakeTeam('First', 'ONE', wins=3, losses=0),
                                      FakeTeam('Second', 'TWO', wins=2, losses=1)])
        table, = tables.standings_tables(league)
        assert table.title == 'Current Standings'
        assert table.rows == [['1', '3-0', 'First'], ['2', '2-1', 'Second']]

    def test_trailing_space_in_a_team_name_does_not_double_up(self):
        league = FakeStandingsLeague([
            FakeTeam('Padded ', 'PAD', wins=1, losses=0, division_id=1, division_name='East'),
            FakeTeam('Bravo', 'BRV', wins=1, losses=0, division_id=2, division_name='West'),
        ])
        assert tables.standings_tables(league)[0].rows[0][2] == f'Padded {espn.DIVISION_LEADER}'

    def test_whitespace_only_team_name_is_not_an_empty_cell(self):
        table, = tables.standings_tables(FakeStandingsLeague([FakeTeam('   ', 'X')]))
        assert table.rows[0][2] == '-'

    def test_empty_team_name_is_not_an_empty_cell(self):
        table, = tables.standings_tables(FakeStandingsLeague([FakeTeam('', 'X')]))
        assert table.rows[0][2] == '-'


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
