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
