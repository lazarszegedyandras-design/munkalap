"""Exercise the real must_fail function without a PostgreSQL dependency."""
import ast
from pathlib import Path
import types
import unittest

ROOT=Path(__file__).resolve().parents[2]


class DbError(Exception):
    def __init__(self, code):
        self.pgcode=code


class Cursor:
    def __init__(self, code):
        self.code=code;self.calls=[]
    def execute(self, sql):
        self.calls.append(sql)
        if sql.startswith("CREATE") and self.code:
            raise DbError(self.code)


class PrivilegeProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse((ROOT/'backend/scripts/check_db_privileges.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='must_fail')
        ns={'psycopg2':types.SimpleNamespace(Error=DbError)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<real must_fail source>','exec'),ns)
        cls.probe=staticmethod(ns['must_fail'])

    def test_insufficient_privilege_is_the_only_expected_failure(self):
        cur=Cursor('42501');self.probe(cur,'CREATE TABLE public.test_fixture(id int)')
        self.assertIn('ROLLBACK TO SAVEPOINT security_privilege_check',cur.calls)

    def test_syntax_error_is_not_a_security_pass(self):
        with self.assertRaises(RuntimeError):self.probe(Cursor('42601'),'CREATE TABLE invalid')

    def test_missing_object_is_not_a_security_pass(self):
        with self.assertRaises(RuntimeError):self.probe(Cursor('42P01'),'CREATE TABLE invalid')

    def test_successful_forbidden_ddl_fails_the_check(self):
        with self.assertRaises(RuntimeError):self.probe(Cursor(None),'CREATE TABLE public.test_fixture(id int)')
