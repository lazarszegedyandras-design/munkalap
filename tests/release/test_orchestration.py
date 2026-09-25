"""Orchestration tests use a fake Docker process, NOT a Docker/PG acceptance."""
from __future__ import annotations
import hashlib
import io
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import release_tests
from promote_tested_images import validate_report


class OrchestrationTests(unittest.TestCase):
    def simulation(self, failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir()
            files={'VERSION':'0.30.1\n','frontend/tests/a.test.js':'// fixture\n','mobile/tests/b.test.js':'// fixture\n'}
            hashes={}
            for name,content in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
                hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            manifest={'format':1,'version':'0.30.1','files':hashes}
            raw=json.dumps(manifest);(root/'release-source-manifest.json').write_text(raw)
            digest=hashlib.sha256(raw.encode()).hexdigest()
            calls=[]
            def docker(argv,**kwargs):
                calls.append(argv)
                text='';code=0
                if argv[1:3]==['image','inspect']:
                    text=json.dumps([{'Id':'sha256:'+hashlib.sha256(argv[-1].encode()).hexdigest(),
                        'Config':{'Labels':{'hu.lunait.release.source-sha256':digest}}}])
                elif '--format' in argv and argv[-1]=='json' and 'config' in argv:
                    text=Path(argv[argv.index('-f')+1]).read_text()
                elif failure=='unit' and '/suite/backend/tests' in argv:
                    code=1;text='simulated test failure'
                elif failure=='migrate' and argv[-1]=='migrate' and 'run' in argv:
                    code=1;text='simulated migration failure'
                return subprocess.CompletedProcess(argv,code,text)
            output=Path(tmp)/'out'
            with patch.object(release_tests,'ROOT',root),patch('release_tests.subprocess.run',side_effect=docker), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code=release_tests.main(['--output',str(output)])
            report=json.loads((output/'report.json').read_text())
            return code,report,calls

    def test_full_plan_dispatches_actual_requested_commands(self):
        code,report,calls=self.simulation()
        self.assertEqual(code,0);self.assertEqual(report['status'],'PASS_REQUESTED_SCOPE')
        validate_report(report,'0.30.1',report['source_manifest_sha256'])
        units=[a for a in calls if '/suite/backend/tests' in a]
        self.assertEqual(len(units),1)
        self.assertEqual(units[0][units[0].index('--entrypoint')+1],'python')
        self.assertIn('-m',units[0]);self.assertIn('pytest',units[0])
        migrate=[a for a in calls if a[-1]=='migrate' and 'run' in a]
        self.assertEqual(len(migrate),4)
        self.assertTrue(all('--entrypoint' not in a for a in migrate))
        self.assertEqual(sum(a[-1]=='assert-head' for a in calls),2)
        self.assertEqual(sum(a[-1]=='compare-snapshot' for a in calls),2)
        self.assertFalse(report['production_go'])

    def test_unit_failure_cannot_become_pass_or_be_promoted(self):
        code,report,_=self.simulation('unit')
        self.assertEqual(code,1);self.assertEqual(report['status'],'FAIL')
        with self.assertRaises(ValueError):validate_report(report,'0.30.1',report['source_manifest_sha256'])

    def test_migration_failure_always_cleans_up_own_project(self):
        code,report,calls=self.simulation('migrate')
        self.assertEqual(code,2);self.assertEqual(report['status'],'BLOCKED')
        cleanup=[a for a in calls if 'down' in a]
        self.assertTrue(cleanup)
        for call in cleanup:
            self.assertTrue(call[call.index('--project-name')+1].startswith('munkalap-test-'))
            self.assertNotIn('-v',call);self.assertNotIn('--volumes',call)
            self.assertNotIn('prune',call)

    def test_every_compose_command_uses_one_explicit_nonproduction_file(self):
        _,_,calls=self.simulation()
        for call in calls:
            if call[:2]!=['docker','compose'] or call[-1]=='version':continue
            self.assertEqual(call.count('-f'),1)
            self.assertIn('--env-file',call)
            self.assertNotIn('.env.production',' '.join(call))
            self.assertNotIn('docker-compose.yml',' '.join(call))

    def test_partial_scope_and_source_mismatch_are_not_promotable(self):
        _,report,_=self.simulation()
        with self.assertRaises(ValueError):validate_report(report,'0.30.2',report['source_manifest_sha256'])
        report['scope']='unit'
        with self.assertRaises(ValueError):validate_report(report,'0.30.1',report['source_manifest_sha256'])
