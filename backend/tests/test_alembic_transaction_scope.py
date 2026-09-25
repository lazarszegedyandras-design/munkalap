from pathlib import Path
import ast


def _run_migrations_online_node():
    path = Path(__file__).resolve().parents[1] / "migrations" / "env.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_migrations_online":
            return node
    raise AssertionError("run_migrations_online() not found")


def test_set_role_is_inside_alembic_transaction_scope():
    """Regression for SQLAlchemy 2.x autobegin rolling migrations back.

    SET ROLE must not execute before Alembic opens its transaction. Otherwise
    connection.execute() creates an implicit outer transaction that is rolled
    back when the connection closes, even though Alembic logs every revision.
    """
    node = _run_migrations_online_node()

    begin_with = None
    for candidate in ast.walk(node):
        if isinstance(candidate, ast.With):
            for item in candidate.items:
                expr = item.context_expr
                if (
                    isinstance(expr, ast.Call)
                    and isinstance(expr.func, ast.Attribute)
                    and isinstance(expr.func.value, ast.Name)
                    and expr.func.value.id == "context"
                    and expr.func.attr == "begin_transaction"
                ):
                    begin_with = candidate
                    break
        if begin_with is not None:
            break

    assert begin_with is not None, "Alembic context.begin_transaction() is required"

    set_role_calls = []
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call) or not isinstance(candidate.func, ast.Attribute):
            continue
        if candidate.func.attr != "execute" or not candidate.args:
            continue
        arg = candidate.args[0]
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Name)
            and arg.func.id == "text"
            and arg.args
            and isinstance(arg.args[0], ast.Constant)
            and arg.args[0].value == "SET ROLE workapp_owner"
        ):
            set_role_calls.append(candidate)

    assert len(set_role_calls) == 1
    set_role = set_role_calls[0]
    assert begin_with.lineno < set_role.lineno <= getattr(begin_with, "end_lineno", set_role.lineno)


def test_no_connection_execute_precedes_alembic_transaction():
    node = _run_migrations_online_node()
    begin_line = None
    for candidate in ast.walk(node):
        if isinstance(candidate, ast.With):
            for item in candidate.items:
                expr = item.context_expr
                if (
                    isinstance(expr, ast.Call)
                    and isinstance(expr.func, ast.Attribute)
                    and isinstance(expr.func.value, ast.Name)
                    and expr.func.value.id == "context"
                    and expr.func.attr == "begin_transaction"
                ):
                    begin_line = candidate.lineno
                    break
        if begin_line is not None:
            break

    assert begin_line is not None
    for candidate in ast.walk(node):
        if (
            isinstance(candidate, ast.Call)
            and isinstance(candidate.func, ast.Attribute)
            and isinstance(candidate.func.value, ast.Name)
            and candidate.func.value.id == "connection"
            and candidate.func.attr == "execute"
        ):
            assert candidate.lineno > begin_line, (
                "connection.execute() before Alembic transaction can trigger SQLAlchemy autobegin "
                "and cause the migration to be rolled back on connection close"
            )
