from pathlib import Path
import ast


def _revision_id(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "revision":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    return None


def test_alembic_revision_ids_fit_default_version_column():
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    revisions = []
    for path in sorted(versions.glob("*.py")):
        revision = _revision_id(path)
        if revision:
            revisions.append((path.name, revision))
    assert revisions
    too_long = [(name, revision, len(revision)) for name, revision in revisions if len(revision) > 32]
    assert too_long == [], f"Alembic revision ID exceeds VARCHAR(32): {too_long}"


def _down_revision(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "down_revision":
                    if isinstance(node.value, ast.Constant):
                        return node.value.value
                    if isinstance(node.value, (ast.Tuple, ast.List)):
                        values = []
                        for item in node.value.elts:
                            if isinstance(item, ast.Constant):
                                values.append(item.value)
                        return tuple(values)
    return None


def test_alembic_graph_has_exactly_one_head():
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    revisions = {}
    referenced = set()
    for path in sorted(versions.glob("*.py")):
        revision = _revision_id(path)
        if not revision:
            continue
        assert revision not in revisions, f"Duplicate Alembic revision ID: {revision}"
        revisions[revision] = path.name
        down = _down_revision(path)
        if isinstance(down, tuple):
            referenced.update(x for x in down if x)
        elif down:
            referenced.add(down)
    heads = sorted(set(revisions) - referenced)
    assert len(heads) == 1, f"Expected one Alembic head, found {heads}"
