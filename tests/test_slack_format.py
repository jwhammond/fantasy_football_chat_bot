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
