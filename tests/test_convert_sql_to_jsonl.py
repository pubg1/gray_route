import textwrap

from scripts.convert_sql_to_jsonl import iter_insert_statements


def test_iter_insert_handles_semicolon_inside_string():
    sql = textwrap.dedent(
        """
        INSERT INTO `case_recovery` VALUES (1, 'foo;bar', 'baz');
        """
    )

    statements = list(iter_insert_statements(sql))

    assert len(statements) == 1
    assert statements[0].values[1] == "foo;bar"
