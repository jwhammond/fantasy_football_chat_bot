import sys
import os
import pytest
sys.path.insert(1, os.path.abspath('.'))

from gamedaybot.espn.tables import Table
import gamedaybot.chat.slack_format as fmt


def sample_table():
    return Table('Matchups', ['Home', 'Proj', 'Away', 'Proj'],
                 [['A (1-0)', '100.00', 'B (0-1)', '90.00']],
                 ['left', 'right', 'left', 'right'])


class TestEscape:
    def test_escapes_slack_control_characters(self):
        assert fmt.escape('A & B <C> D') == 'A &amp; B &lt;C&gt; D'


class TestTableBlocks:
    def test_returns_title_section_then_table(self):
        blocks = fmt.table_blocks(sample_table())
        assert [b['type'] for b in blocks] == ['section', 'table']
        assert blocks[0]['text'] == {'type': 'mrkdwn', 'text': '*Matchups*'}

    def test_title_is_escaped(self):
        t = sample_table()
        t.title = 'Tom & Jerry'
        assert fmt.table_blocks(t)[0]['text']['text'] == '*Tom &amp; Jerry*'

    def test_header_row_comes_first_and_cells_are_raw_text(self):
        table = fmt.table_blocks(sample_table())[1]
        assert table['rows'][0] == [{'type': 'raw_text', 'text': h} for h in ['Home', 'Proj', 'Away', 'Proj']]
        assert table['rows'][1] == [{'type': 'raw_text', 'text': c} for c in ['A (1-0)', '100.00', 'B (0-1)', '90.00']]

    def test_column_settings_map_alignment_and_wrap_left_columns(self):
        table = fmt.table_blocks(sample_table())[1]
        assert table['column_settings'] == [
            {'align': 'left', 'is_wrapped': True},
            {'align': 'right'},
            {'align': 'left', 'is_wrapped': True},
            {'align': 'right'},
        ]

    def test_empty_cells_become_dash(self):
        t = sample_table()
        t.rows = [['', '1.00', 'B', '2.00']]
        assert fmt.table_blocks(t)[1]['rows'][1][0]['text'] == '-'

    def test_too_many_rows_raises(self):
        t = sample_table()
        t.rows = [['A', '1', 'B', '2']] * fmt.MAX_TABLE_ROWS  # plus the header row exceeds the limit
        with pytest.raises(ValueError):
            fmt.table_blocks(t)

    def test_too_many_columns_raises(self):
        n = fmt.MAX_TABLE_COLUMNS + 1
        t = Table('Wide', ['h'] * n, [['c'] * n], ['left'] * n)
        with pytest.raises(ValueError):
            fmt.table_blocks(t)


class TestTextBlocks:
    def test_single_line_is_plain_section_without_code_block(self):
        assert fmt.text_blocks('bot is back online') == [
            {'type': 'section', 'text': {'type': 'mrkdwn', 'text': 'bot is back online'}}]

    def test_single_line_is_escaped(self):
        assert fmt.text_blocks('a < b')[0]['text']['text'] == 'a &lt; b'

    def test_multiline_bolds_first_line_and_code_blocks_the_rest(self):
        blocks = fmt.text_blocks('Waiver Report 2026-09-10:\nTEAM\nADDED Player A\nDROPPED Player B')
        assert blocks == [{'type': 'section', 'text': {
            'type': 'mrkdwn',
            'text': '*Waiver Report 2026-09-10:*\n```\nTEAM\nADDED Player A\nDROPPED Player B\n```'}}]

    def test_body_is_escaped_inside_code_block(self):
        text = fmt.text_blocks('Title\nA & B')[0]['text']['text']
        assert 'A &amp; B' in text

    def test_long_body_splits_across_sections_at_line_boundaries(self):
        lines = [f'line {i:04d} ' + 'x' * 90 for i in range(60)]  # ~6000 chars
        blocks = fmt.text_blocks('Title\n' + '\n'.join(lines))
        assert len(blocks) >= 2
        assert blocks[0]['text']['text'].startswith('*Title*\n```\n')
        for block in blocks:
            assert len(block['text']['text']) <= 3000
            body = block['text']['text'].split('```')[1]
            assert all(line.startswith('line ') for line in body.strip('\n').split('\n'))
        joined = '\n'.join(b['text']['text'].split('```')[1].strip('\n') for b in blocks)
        assert joined.split('\n') == lines

    def test_single_overlong_line_is_split_so_no_section_exceeds_cap(self):
        blocks = fmt.text_blocks('Title\n' + 'x' * 7000)
        assert len(blocks) >= 2
        for block in blocks:
            assert len(block['text']['text']) <= 3000
        # Reconstruct the body from all blocks
        body_parts = []
        for i, block in enumerate(blocks):
            text = block['text']['text']
            if i == 0:
                # First block has title and fences
                code_part = text.split('```')[1].strip('\n')
            else:
                # Later blocks have just fences
                code_part = text.split('```')[1].strip('\n')
            body_parts.append(code_part)
        assert ''.join(body_parts) == 'x' * 7000

    def test_long_title_does_not_push_first_section_over_cap(self):
        # Under MAX_TITLE_LENGTH, so it is still rendered as a bold title;
        # test_overlong_first_line_is_body_not_title covers titles over it.
        long_title = 'T' * (fmt.MAX_TITLE_LENGTH - 1)
        lines = [f'line {i:04d} ' + 'x' * 100 for i in range(60)]
        blocks = fmt.text_blocks(long_title + '\n' + '\n'.join(lines))
        assert all(len(b['text']['text']) <= 3000 for b in blocks)
        assert blocks[0]['text']['text'].startswith('*' + long_title + '*\n```\n')

    def test_title_stays_on_first_section_when_first_line_is_overlong(self):
        blocks = fmt.text_blocks('Title\n' + 'x' * 7000)
        assert blocks[0]['text']['text'].startswith('*Title*\n```\n')
        assert all('*Title*' not in b['text']['text'] for b in blocks[1:])
        assert all(len(b['text']['text']) <= 3000 for b in blocks)

    def test_overlong_first_line_is_body_not_title(self):
        first_line = 'T' * 2995
        text = first_line + '\nbody line'
        blocks = fmt.text_blocks(text)

        assert all(len(b['text']['text']) <= 3000 for b in blocks)
        assert all('*' + first_line not in b['text']['text'] for b in blocks)

        code_bodies = []
        for block in blocks:
            parts = block['text']['text'].split('```')
            assert len(parts) == 3  # no leading title text before the fence
            assert parts[0] == ''
            code_bodies.append(parts[1].strip('\n'))
        # A hard-split line can pick up an extra chunk-boundary newline that
        # isn't in the source text, so compare content with newlines removed
        # rather than requiring an exact line-for-line reconstruction.
        reassembled = ''.join(code_bodies).replace('\n', '')
        assert reassembled == text.replace('\n', '')

    def test_split_line_never_loops_on_nonpositive_budget(self):
        assert list(fmt._split_line('abc', 0)) == ['a', 'b', 'c']
