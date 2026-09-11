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


# Slack caps a section's text at 3000 characters. Code-block bodies are split
# below this so the fence characters and title fit alongside them.
SECTION_BODY_LIMIT = 2900


def _section(text):
    return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}


def _chunk_lines(lines, limit):
    """Group lines into chunks whose joined length stays within limit."""
    chunks, current, size = [], [], 0
    for line in lines:
        if current and size + len(line) + 1 > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append(current)
    return chunks


def text_blocks(text):
    """Render a text report: a lone line as plain text, otherwise a bold title
    over a code block that preserves the report's column alignment."""
    lines = escape(text).split('\n')
    if len(lines) == 1:
        return [_section(lines[0])]
    title, body = lines[0], lines[1:]
    blocks = []
    for index, chunk in enumerate(_chunk_lines(body, SECTION_BODY_LIMIT)):
        code = '```\n' + '\n'.join(chunk) + '\n```'
        blocks.append(_section(f'*{title}*\n{code}' if index == 0 else code))
    return blocks
