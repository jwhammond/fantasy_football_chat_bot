"""Render bot reports as Slack Block Kit blocks.

Pure functions: no network, no environment. Slack's table block was probed
against a live incoming webhook on 2026-09-11; see
docs/superpowers/specs/2026-09-11-slack-table-formatting-design.md for what
it accepts (raw_text cells only, no empty cells, 100 rows, 20 columns).
"""

MAX_TABLE_ROWS = 100      # including the header row
MAX_TABLE_COLUMNS = 20
EMPTY_CELL = '-'


def escape(text):
    """Escape the three characters Slack treats as control characters in text."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _title_section(title):
    return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*{escape(title)}*'}}


def _raw_text(cell):
    return {'type': 'raw_text', 'text': cell if cell else EMPTY_CELL}


def table_blocks(table):
    """A bold title section followed by a table block for the given Table."""
    rows = [table.headers] + table.rows
    if len(rows) > MAX_TABLE_ROWS:
        raise ValueError(f"Slack tables allow {MAX_TABLE_ROWS} rows including the header; got {len(rows)}")
    if len(table.headers) > MAX_TABLE_COLUMNS:
        raise ValueError(f"Slack tables allow {MAX_TABLE_COLUMNS} columns; got {len(table.headers)}")

    column_settings = []
    for align in table.align:
        setting = {'align': align}
        if align == 'left':
            setting['is_wrapped'] = True
        column_settings.append(setting)

    return [
        _title_section(table.title),
        {
            'type': 'table',
            'column_settings': column_settings,
            'rows': [[_raw_text(cell) for cell in row] for row in rows],
        },
    ]
