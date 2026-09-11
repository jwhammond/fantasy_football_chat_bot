import pytest
import sys
import os
sys.path.insert(1, os.path.abspath('.'))
from gamedaybot.chat.slack import (Slack, SlackException, )


@pytest.mark.usefixtures("mock_requests")
class TestSlack:
    '''Test SlackBot class'''

    def setup_method(self):
        self.url = "https://hooks.slack.com/services/A1B2C3/ABC1ABC2/abcABC1abcABC2"
        self.test_bot = Slack(self.url)
        self.test_text = "This is a test."

    def test_send_message(self, mock_requests):
        '''Does the message send successfully?'''
        mock_requests.post(self.url, status_code=200)
        assert self.test_bot.send_message(self.test_text).status_code == 200

    def test_send_message_posts_blocks_with_plain_fallback(self, mock_requests):
        mock_requests.post(self.url, status_code=200)
        self.test_bot.send_message("Title\nrow one")
        body = mock_requests.last_request.json()
        assert body["text"] == "Title\nrow one"
        assert body["blocks"] == [{"type": "section", "text": {
            "type": "mrkdwn", "text": "*Title*\n```\nrow one\n```"}}]

    def test_send_blocks_posts_given_blocks_and_fallback(self, mock_requests):
        mock_requests.post(self.url, status_code=200)
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*Hi*"}}]
        assert self.test_bot.send_blocks(blocks, fallback="Hi").status_code == 200
        assert mock_requests.last_request.json() == {"text": "Hi", "blocks": blocks}

    def test_send_blocks_raises_on_error(self, mock_requests):
        mock_requests.post(self.url, status_code=400, text="invalid_blocks")
        with pytest.raises(SlackException):
            self.test_bot.send_blocks([], fallback="x")

    def test_unset_webhook_sends_nothing(self, mock_requests):
        for unset in (1, "1", ""):
            assert Slack(unset).send_blocks([], fallback="x") is None
            assert Slack(unset).send_message("x") is None
        assert mock_requests.call_count == 0

    def test_bad_bot_id(self, mock_requests):
        '''Does the expected error raise when a bot id is incorrect?'''
        mock_requests.post(self.url, status_code=404)
        with pytest.raises(SlackException):
            self.test_bot.send_message(self.test_text)
