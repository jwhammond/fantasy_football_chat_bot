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


# Slack caps a section's text at 3000 characters.
SECTION_TEXT_LIMIT = 3000


def _section(text):
    return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}


def _split_line(line, budget):
    """Yield pieces of a line that each fit within the budget."""
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


def text_blocks(text):
    """Render a text report: a lone line as plain text, otherwise a bold title
    over a code block that preserves the report's column alignment."""
    lines = escape(text).split('\n')
    if len(lines) == 1:
        return [_section(lines[0])]
    title, body = lines[0], lines[1:]

    # Calculate budgets for body chunks accounting for title and fences
    title_overhead = len(f'*{title}*\n')
    fence_overhead = len('```\n') + len('\n```')
    first_budget = SECTION_TEXT_LIMIT - title_overhead - fence_overhead
    later_budget = SECTION_TEXT_LIMIT - fence_overhead

    # Chunk the body lines
    chunks = _chunk_lines(body, first_budget, later_budget)

    # Render blocks: title on first chunk, code block on all chunks
    blocks = []
    for index, chunk in enumerate(chunks):
        code = '```\n' + '\n'.join(chunk) + '\n```'
        if index == 0:
            blocks.append(_section(f'*{title}*\n{code}'))
        else:
            blocks.append(_section(code))

    return blocks
