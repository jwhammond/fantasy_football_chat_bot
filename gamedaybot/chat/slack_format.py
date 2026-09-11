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


def _chunk_lines(lines, budget):
    """Group lines into chunks that fit within budget, hard-splitting overlong lines.

    Each chunk's joined length (lines plus newlines between them) must fit within
    the budget. Lines longer than the budget are split at character boundaries.
    """
    chunks, current, size = [], [], 0
    for line in lines:
        # If this single line exceeds the budget, hard-split it.
        if len(line) > budget:
            # Flush current chunk first
            if current:
                chunks.append(current)
                current, size = [], 0
            # Split the overlong line into chunks that fit the budget
            while len(line) > budget:
                chunks.append([line[:budget]])
                line = line[budget:]
            # Remaining part (if any) goes into a new current chunk
            if line:
                current, size = [line], len(line)
        # If adding this line would exceed budget (accounting for newline), start a new chunk
        elif current and size + len(line) + 1 > budget:
            chunks.append(current)
            current, size = [line], len(line)
        else:
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

    # Calculate budgets for body chunks accounting for title and fences
    title_overhead = len(f'*{title}*\n')
    fence_overhead = len('```\n') + len('\n```')
    first_budget = SECTION_TEXT_LIMIT - title_overhead - fence_overhead
    later_budget = SECTION_TEXT_LIMIT - fence_overhead

    # Chunk body with dynamic budgets: first section uses first_budget, others use later_budget
    blocks = []
    current_chunk = []
    current_size = 0
    is_first_section = True

    for line in body:
        budget = first_budget if is_first_section else later_budget

        # Hard-split any line that exceeds the budget
        if len(line) > budget:
            if current_chunk:
                # Flush current chunk and switch to later budget if this was first section
                code = '```\n' + '\n'.join(current_chunk) + '\n```'
                if is_first_section:
                    blocks.append(_section(f'*{title}*\n{code}'))
                    is_first_section = False
                else:
                    blocks.append(_section(code))
                current_chunk = []
                current_size = 0
                budget = later_budget  # Switch to later budget

            # Split the overlong line
            while len(line) > budget:
                code = '```\n' + line[:budget] + '\n```'
                blocks.append(_section(code))
                line = line[budget:]

            # Remaining part goes into new chunk
            if line:
                current_chunk = [line]
                current_size = len(line)
        # Normal line: check if it fits in current chunk
        elif current_chunk and current_size + len(line) + 1 > budget:
            # Flush current chunk
            code = '```\n' + '\n'.join(current_chunk) + '\n```'
            if is_first_section:
                blocks.append(_section(f'*{title}*\n{code}'))
                is_first_section = False
            else:
                blocks.append(_section(code))
            current_chunk = [line]
            current_size = len(line)
        else:
            current_chunk.append(line)
            current_size += len(line) + 1

    # Flush remaining chunk
    if current_chunk:
        code = '```\n' + '\n'.join(current_chunk) + '\n```'
        if is_first_section:
            blocks.append(_section(f'*{title}*\n{code}'))
        else:
            blocks.append(_section(code))

    return blocks
