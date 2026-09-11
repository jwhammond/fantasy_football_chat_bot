import requests
import json
import logging
import os

if os.environ.get("AWS_EXECUTION_ENV") is not None:
    from chat.slack_format import text_blocks
else:
    import sys
    sys.path.insert(1, os.path.abspath('.'))
    from gamedaybot.chat.slack_format import text_blocks

logger = logging.getLogger(__name__)


class SlackException(Exception):
    pass


class Slack:
    """
    Send messages to a Slack channel through an incoming webhook.

    Parameters
    ----------
    webhook_url : str
        The URL of the Slack webhook to send messages to. 1, "1" or "" means
        Slack is not configured and sends are silently skipped.
    """

    UNSET = (1, "1", "")

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def __repr__(self):
        return "Slack Webhook Url(%s)" % self.webhook_url

    def send_blocks(self, blocks, fallback: str):
        """
        Post Block Kit blocks to the channel.

        Parameters
        ----------
        blocks : list of dict
            Block Kit blocks, e.g. from gamedaybot.chat.slack_format.
        fallback : str
            Plain text Slack shows in notifications and clients that cannot
            render blocks.

        Returns
        -------
        requests.Response, or None when the webhook is not configured.

        Raises
        ------
        SlackException
            If Slack returns anything other than 200.
        """
        if self.webhook_url in self.UNSET:
            return None

        payload = {"text": fallback, "blocks": blocks}
        headers = {'content-type': 'application/json'}
        r = requests.post(self.webhook_url, data=json.dumps(payload), headers=headers)

        if r.status_code != 200:
            logger.error(r.content)
            raise SlackException(r.content)

        return r

    def send_message(self, text: str):
        """
        Send a text report. Multi-line reports get a bold first line over a
        code block; a single line is sent as plain text.
        """
        return self.send_blocks(text_blocks(text), fallback=text)
