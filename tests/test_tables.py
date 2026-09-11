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
