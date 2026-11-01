"""A separate catalogue must be reproducible without changing launch authority."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import sync_components as sync
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('catalog_integrity', ROOT / 'IRGS_Catalog/verify_catalog.py')
integrity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integrity)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE).decode().strip()


def repository(root, files):
    root.mkdir()
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Synthetic QA')
    git(root, 'config', 'user.email', 'qa@irgs.invalid')
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'Synthetic component fixture')
    return git(root, 'rev-parse', 'HEAD')


class CatalogBoundaryTests(unittest.TestCase):
    def test_changed_or_unbound_content_is_rejected_without_an_app(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'IRGS_Catalog'
            shutil.copytree(ROOT / 'IRGS_Catalog', root, ignore=shutil.ignore_patterns('__pycache__'))
            self.assertEqual(integrity.verify_catalog(root)['concepts'], 44)
            path = root / 'data/campaign_portfolio.json'
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
                integrity.verify_catalog(root)
            path.write_bytes(original)
            (root / 'data/unbound.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'inventory differs'):
                integrity.verify_catalog(root)

    def test_explicit_missing_dependency_fails_instead_of_using_joined_content(self):
        command = [sys.executable, '-B', '-c',
            "import sys;sys.path.insert(0,'IRGS_Web');import catalog_paths"]
        environment = dict(os.environ, IRGS_CATALOG_ROOT='/nonexistent/synthetic-catalog')
        result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('IRGS Catalog is unavailable', result.stderr)

    @unittest.skipUnless(os.name == 'posix', 'Cloud watcher uses POSIX file locks and process groups')
    def test_qa_assembly_uses_selected_catalog_instead_of_joined_copy(self):
        import watch_component_qa as watcher
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            engine, app, catalog, joined = (base / name for name in ('engine', 'app', 'catalog', 'joined'))
            refs = {'engine': repository(engine, {'IRGS_3_3/engine.txt': 'engine',
                'engine/design.md': 'design', 'provenance/source.md': 'source',
                'ROADMAP.md': 'roadmap', 'CONTINUATION_STATUS.md': 'status', 'DEVELOPMENT_LIST.md': 'list'}),
                'app': repository(app, {'IRGS_Web/view.txt': 'viewer', 'Start-IRGS.cmd': 'launcher'}),
                'catalog': repository(catalog, {'IRGS_Catalog/data.json': 'selected catalogue'}),
                'joined': repository(joined, {'IRGS_Catalog/obsolete.json': 'old catalogue',
                    'provenance/qa/current_report.md': 'retained integration QA',
                    'COMPONENTS.json': json.dumps({n: {} for n in ('engine', 'app', 'catalog')}),
                    # This test exercises assembly, not the separate source verifier.
                    'tools/verify_development.py': "print('{}')"})}
            args = SimpleNamespace(engine=engine, app=app, catalog=catalog, joined=joined)
            run = base / 'run'
            run.mkdir()
            candidate, commit = watcher.assemble(args, refs, run)
            self.assertEqual((candidate / 'IRGS_Catalog/data.json').read_text(), 'selected catalogue')
            self.assertFalse((candidate / 'IRGS_Catalog/obsolete.json').exists())
            self.assertEqual((candidate / 'provenance/qa/current_report.md').read_text(), 'retained integration QA')
            self.assertEqual(json.loads((candidate / 'COMPONENTS.json').read_text())['catalog']['commit'], refs['catalog'])
            self.assertEqual(git(candidate, 'rev-parse', 'HEAD'), commit)

    def test_sync_requires_catalog_pin_and_preserves_unrelated_joined_source(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            engine, app, catalog, joined = (base / name for name in ('engine', 'app', 'catalog', 'joined'))
            e = repository(engine, {'IRGS_3_3/source.txt': 'engine',
                'provenance/source.md': 'selected Engine provenance',
                'provenance/qa/current_report.md': 'stale component QA',
                'engine/qualification/operation_register.json': 'stale operation register',
                'engine/OPERATION_COVERAGE.md': 'stale operation coverage',
                'provenance/coordination/owners/app/COORDINATOR_WORK_ORDER.md': 'stale component copy'})
            c = repository(catalog, {'IRGS_Catalog/data.json': 'current catalog'})
            repository(app, {'IRGS_Web/view.txt': 'viewer'})
            git(app, 'clone', '--quiet', '--no-hardlinks', str(engine), 'Engine')
            git(app, 'clone', '--quiet', '--no-hardlinks', str(catalog), 'Catalog')
            for name, commit in (('Engine', e), ('Catalog', c)):
                git(app, 'update-index', '--add', '--cacheinfo', '160000,' + commit + ',' + name)
            git(app, 'commit', '-qm', 'Pin both synthetic dependencies')
            commits = {'engine': e, 'app': git(app, 'rev-parse', 'HEAD'), 'catalog': c}
            cycle = {'schema_version': 1, 'cycle_id': 'synthetic-qualification',
                'baseline_components': {name: '0' * 40 for name in commits},
                'reviews': {name: {'status': 'approved', 'commit': commit,
                    'deliverable': 'component_update', 'checks': [{'status': 'passed'}]}
                    for name, commit in commits.items()}}
            repository(joined, {'IRGS_Catalog/old.json': 'obsolete', 'keep.txt': 'retained',
                'provenance/qa/current_report.md': 'retained QA',
                'provenance/obsolete.md': 'obsolete Engine provenance',
                'engine/qualification/operation_register.json': 'current joined register',
                'engine/OPERATION_COVERAGE.md': 'current joined coverage',
                'provenance/coordination/owners/app/COORDINATOR_WORK_ORDER.md': 'current joined handoff',
                'provenance/coordination/target_5_0/ENGINE.md': 'current joined target',
                'COORDINATION.json': json.dumps(cycle),
                'COMPONENTS.json': json.dumps({n: {} for n in ('engine', 'app', 'catalog')})})
            with patch.object(sync, 'ROOT', joined):
                planned = sync.sync(engine, app, catalog)
                self.assertIn('IRGS_Catalog/old.json', planned['removed_paths'])
                self.assertIn('provenance/obsolete.md', planned['removed_paths'])
                self.assertFalse(any(name in planned['changed_paths'] + planned['removed_paths']
                    for name in ('engine/qualification/operation_register.json', 'engine/OPERATION_COVERAGE.md', 'provenance/qa/current_report.md')))
                self.assertFalse(any(name.startswith('provenance/coordination/')
                    for name in planned['changed_paths'] + planned['removed_paths']))
                self.assertFalse((joined / 'IRGS_Catalog/data.json').exists())
                cycle['reviews']['catalog']['status'] = 'pending'
                (joined / 'COORDINATION.json').write_text(json.dumps(cycle))
                git(joined, 'add', '.')
                git(joined, 'commit', '-qm', 'Hold one synthetic component review')
                with self.assertRaisesRegex(ValueError, 'Unified integration is held'):
                    sync.sync(engine, app, catalog, apply=True)
                self.assertFalse((joined / 'IRGS_Catalog/data.json').exists())
                self.assertTrue((joined / 'IRGS_Catalog/old.json').exists())
                cycle['reviews']['catalog']['status'] = 'approved'
                (joined / 'COORDINATION.json').write_text(json.dumps(cycle))
                git(joined, 'add', '.')
                git(joined, 'commit', '-qm', 'Approve complete synthetic component set')
                sync.sync(engine, app, catalog, apply=True)
                self.assertEqual((joined / 'IRGS_Catalog/data.json').read_text(), 'current catalog')
                self.assertFalse((joined / 'IRGS_Catalog/old.json').exists())
                self.assertEqual((joined / 'keep.txt').read_text(), 'retained')
                self.assertEqual((joined / 'provenance/qa/current_report.md').read_text(), 'retained QA')
                self.assertEqual((joined / 'provenance/source.md').read_text(), 'selected Engine provenance')
                self.assertFalse((joined / 'provenance/obsolete.md').exists())
                self.assertEqual((joined / 'engine/qualification/operation_register.json').read_text(), 'current joined register')
                self.assertEqual((joined / 'engine/OPERATION_COVERAGE.md').read_text(), 'current joined coverage')
                self.assertEqual((joined / 'provenance/coordination/owners/app/COORDINATOR_WORK_ORDER.md').read_text(), 'current joined handoff')
                self.assertEqual((joined / 'provenance/coordination/target_5_0/ENGINE.md').read_text(), 'current joined target')
                self.assertEqual(json.loads((joined / 'COMPONENTS.json').read_text())['catalog']['commit'], c)
                git(joined, 'add', '.')
                git(joined, 'commit', '-qm', 'Synthetic integration')
                (catalog / 'IRGS_Catalog/data.json').write_text('new unqualified catalog')
                git(catalog, 'add', '.')
                git(catalog, 'commit', '-qm', 'Synthetic next catalogue')
                with self.assertRaisesRegex(ValueError, 'Catalog commit differs'):
                    sync.sync(engine, app, catalog, apply=True)
                self.assertEqual((joined / 'IRGS_Catalog/data.json').read_text(), 'current catalog')


if __name__ == '__main__':
    unittest.main()
