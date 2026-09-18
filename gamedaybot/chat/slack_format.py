"""Render bot reports as Slack Block Kit blocks.

Pure functions: no network, no environment. Slack's table block was probed
against a live incoming webhook on 2026-09-11; see
docs/superpowers/specs/2026-09-11-slack-table-formatting-design.md for what
it accepts (raw_text cells only, no empty cells, 100 rows, 20 columns).
"""

MAX_TABLE_ROWS = 100      # including the header row
MAX_TABLE_COLUMNS = 20
# Intentionally duplicated in espn/tables.py: chat/ must not import espn/,
# so the two modules cannot share this constant.
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


# Slack caps a section's text at 3000 characters.
SECTION_TEXT_LIMIT = 3000

# A first line longer than this is treated as body text rather than a title:
# past this length it reads as data, not a heading, and the "*title*\n" plus
# code fences overhead could otherwise drive the first section's budget to
# zero (or negative).
MAX_TITLE_LENGTH = 200


def _section(text):
    return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}


def _split_line(line, budget):
    """Yield pieces of a line that each fit within the budget.

    budget is clamped to at least 1 so a caller passing a nonpositive budget
    (e.g. from an exhausted first-section budget) can never cause this to
    loop forever yielding empty strings.
    """
    budget = max(1, budget)
    while len(line) > budget:
        yield line[:budget]
        line = line[budget:]
    if line:
        yield line


def _chunk_lines(lines, first_budget, later_budget):
    """Group lines into chunks that fit within budgets, hard-splitting overlong lines.

    The first chunk must fit first_budget; all later chunks must fit later_budget.
    Each chunk's joined length (sum of line lengths plus newlines) is at most its budget.
    A line longer than the current budget is hard-split at character boundaries.
    """
    chunks = []
    current_chunk = []
    current_size = 0
    budget = first_budget

    for line in lines:
        # Hard-split any line that exceeds the current budget
        if len(line) > budget:
            # Flush current chunk if any
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_size = 0
                budget = later_budget

            # Hard-split the overlong line into pieces
            for piece in _split_line(line, budget):
                # Check if this piece fits in the current chunk
                if current_chunk and current_size + len(piece) + 1 > budget:
                    chunks.append(current_chunk)
                    current_chunk = [piece]
                    current_size = len(piece)
                else:
                    current_chunk.append(piece)
                    current_size += len(piece) + 1
        # Normal line: check if it fits in current chunk
        elif current_chunk and current_size + len(line) + 1 > budget:
            # Flush current chunk and switch to later budget if this was the first
            chunks.append(current_chunk)
            budget = later_budget
            current_chunk = [line]
            current_size = len(line)
        else:
            current_chunk.append(line)
            current_size += len(line) + 1

    # Flush remaining chunk
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def list_blocks(labeled):
    """A bold title section followed by the label/value pairs of a LabeledList.

    Each item renders as its bold label over its value, as proportional text
    rather than the monospace code block text_blocks falls back to. Items are
    packed into as few sections as Slack's per-section character cap allows,
    and a label is never separated from its value: an item that would overflow
    the current section starts a new one. An item too large for a section of
    its own is hard-split, which only a malformed report could produce.

    Parameters
    ----------
    labeled : gamedaybot.espn.tables.LabeledList
        The title and (label, value) pairs to render.

    Returns
    -------
    list of dict
        Block Kit blocks: the title section, then one section per chunk of
        items. A LabeledList with no items renders as the title alone.
    """
    blocks = [_title_section(labeled.title)]

    pieces = []
    for label, value in labeled.items:
        piece = f'*{escape(label)}*\n{escape(value)}'
        # An item wider than a whole section cannot be packed; split it so the
        # payload stays valid rather than letting Slack reject the message.
        pieces.extend(_split_line(piece, SECTION_TEXT_LIMIT)
                      if len(piece) > SECTION_TEXT_LIMIT else [piece])

    current, size = [], 0
    for piece in pieces:
        if current and size + len(piece) + 1 > SECTION_TEXT_LIMIT:
            blocks.append(_section('\n'.join(current)))
            current, size = [piece], len(piece)
        else:
            current.append(piece)
            size += len(piece) + 1
    if current:
        blocks.append(_section('\n'.join(current)))

    return blocks


def text_blocks(text):
    """Render a text report: a lone line as plain text, otherwise a bold title
    over a code block that preserves the report's column alignment.

    When the first line is longer than MAX_TITLE_LENGTH it is not a title
    (and could otherwise drive the first section's budget to zero or
    negative): the entire text, first line included, is rendered as
    code-block body across sections with no bold line.
    """
    lines = escape(text).split('\n')
    if len(lines) == 1:
        return [_section(lines[0])]

    fence_overhead = len('```\n') + len('\n```')
    later_budget = SECTION_TEXT_LIMIT - fence_overhead

    if len(lines[0]) > MAX_TITLE_LENGTH:
        body = lines
        first_budget = later_budget
        title = None
    else:
        title, body = lines[0], lines[1:]
        # Calculate budget for the first chunk accounting for title and fences
        title_overhead = len(f'*{title}*\n')
        first_budget = SECTION_TEXT_LIMIT - title_overhead - fence_overhead

    # Chunk the body lines
    chunks = _chunk_lines(body, first_budget, later_budget)

    # Render blocks: title (if any) on first chunk, code block on all chunks
    blocks = []
    for index, chunk in enumerate(chunks):
        code = '```\n' + '\n'.join(chunk) + '\n```'
        if index == 0 and title is not None:
            blocks.append(_section(f'*{title}*\n{code}'))
        else:
            blocks.append(_section(code))

    return blocks
