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

    def test_no_cell_is_empty(self):
        t = tables.matchups_table(None, box_scores=[FakeBox(FakeTeam('', ''), AWAY)])
        assert all(cell for row in t.rows for cell in row)


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
