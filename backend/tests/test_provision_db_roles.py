from psycopg2 import sql

from scripts.provision_db_roles import OWNER_ROLE, transfer_public_objects


class CatalogCursor:
    def __init__(self):
        self.executed = []
        self._rows = []

    def execute(self, statement, params=None):
        self.executed.append((statement, params))
        source = statement if isinstance(statement, str) else ""
        if "c.relkind IN ('r', 'p', 'v', 'm')" in source:
            self._rows = [("r", "serial_table"), ("p", "partitioned_table"), ("m", "materialized_result")]
        elif "c.relkind = 'S'" in source:
            # The catalog query must already have filtered both owned
            # sequences; only the standalone one reaches ALTER SEQUENCE.
            self._rows = [("standalone_sequence",)]
        elif "FROM pg_proc" in source:
            self._rows = []

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


def test_owned_sequences_are_catalog_filtered_and_relations_are_transferred_first():
    cursor = CatalogCursor()

    transfer_public_objects(cursor)

    catalog_queries = [statement for statement, _ in cursor.executed if isinstance(statement, str)]
    sequence_catalog = next(statement for statement in catalog_queries if "c.relkind = 'S'" in statement)
    assert "FROM pg_depend d" in sequence_catalog
    assert "d.refobjsubid > 0" in sequence_catalog
    assert "d.deptype IN ('a', 'i')" in sequence_catalog
    assert "_id_seq" not in sequence_catalog

    composed = [(index, repr(statement)) for index, (statement, _) in enumerate(cursor.executed) if isinstance(statement, sql.Composed)]
    table_index = next(index for index, statement in composed if "ALTER TABLE" in statement)
    sequence_index = next(index for index, statement in composed if "ALTER SEQUENCE" in statement)
    assert table_index < sequence_index

    sequence_commands = [statement for _, statement in composed if "ALTER SEQUENCE" in statement]
    assert len(sequence_commands) == 1
    assert "standalone_sequence" in sequence_commands[0]
    assert "serial_table" not in sequence_commands[0]
    assert "identity" not in sequence_commands[0]
    assert f"Identifier('{OWNER_ROLE}')" in sequence_commands[0]
    assert "Identifier('public', 'standalone_sequence')" in sequence_commands[0]
