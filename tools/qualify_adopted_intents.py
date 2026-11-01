"""Execute unchanged Catalog intent/draft cases against an explicit adopted set.

The original consumer and its original source guards are preserved byte for byte.
A separate subclass binds only this new selection to joined or standalone source.
"""
import argparse
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path)
    for name in ('engine', 'app', 'catalog'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    chosen = json.loads(args.selection.read_text())
    assert chosen['fixture_id'] in {'coordinator-adopted-intent-world-3.4.6-1','coordinator-adopted-intent-world-3.4.7-1','coordinator-adopted-intent-world-3.4.8-1','coordinator-adopted-intent-world-3.4.9-1'}
    if args.source_root:
        root = args.source_root.resolve()
        components = json.loads((root/'COMPONENTS.json').read_text())
        assert all(components[k]['commit'] == chosen['components'][k] for k in ('engine','app','catalog'))
        subprocess.run([sys.executable,'-B',str(root/'tools/verify_development.py')],cwd=root,check=True,stdout=subprocess.DEVNULL)
        engine, app, catalog = root/'IRGS_3_3', root/'IRGS_Web', root/'IRGS_Catalog'
        mode = 'joined_or_clean_extracted_source'
    else:
        assert all((args.engine,args.app,args.catalog))
        roots = {key:getattr(args,key).resolve() for key in ('engine','app','catalog')}
        for key, path in roots.items():
            assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip() == chosen['components'][key]
            assert not subprocess.check_output(['git','status','--porcelain'],cwd=path).strip()
        for key, name in [('engine','Engine'),('catalog','Catalog')]:
            assert subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=roots['app'],text=True).strip() == chosen['components'][key]
        engine, app, catalog = roots['engine']/'IRGS_3_3', roots['app']/'IRGS_Web', roots['catalog']/'IRGS_Catalog'
        mode = 'standalone_exact_clean_sources_and_pins'
    folder = Path(__file__).resolve().parent/'catalog_consumers'
    original = folder/'test_intent_world_draft_cases.py'
    base = folder/'test_current_ordinary_cases.py'
    assert sha(original) == chosen['original_consumer_sha256']
    assert sha(base) == chosen['original_base_consumer_sha256']
    fixture = catalog/'evaluation/intent_world_draft_v1'
    for name, digest in chosen['fixture_files_sha256'].items():
        assert sha(fixture/name) == digest
    os.environ['IRGS_ENGINE_ROOT'] = str(engine)
    os.environ['IRGS_CATALOG_ROOT'] = str(catalog)
    sys.path[:0] = [str(app),str(engine/'runtime'),str(catalog),str(Path(__file__).resolve().parent.parent)]
    current = load('tools.tests.test_current_ordinary_consumers',base)
    import tools.tests
    tools.tests.test_current_ordinary_consumers = current
    module = load('catalog_original_intent_world_cases',original)
    # Validate the unchanged original fixture selection, then qualify the new set
    # separately. Do not execute or alter the original exact-source setup guard.
    module.selection.load_fixture(catalog)

    class AdoptedIntentWorldCases(module.CandidateIntentWorldConsumers):
        __unittest_skip__ = False
        __unittest_skip_why__ = ''

        @classmethod
        def setUpClass(cls):
            for name, path in [('server',app),('solo_provider',engine),('openai_proposals',engine),
                               ('world_draft',engine),('offline_responses',engine),('core_world',engine)]:
                imported = importlib.import_module(name)
                assert Path(imported.__file__).resolve().is_relative_to(path)
                setattr(cls,name,imported)
            ordinary = catalog/'evaluation/current_ordinary_communication_v1'
            cls.cases = json.loads((ordinary/'actor_inputs/cases.json').read_text())
            cls.oracle = json.loads((ordinary/'evaluator_only/expectations.json').read_text())
            cls.inputs = json.loads((fixture/'actor_inputs/cases.json').read_text())
            cls.expected = json.loads((fixture/'evaluator_only/expectations.json').read_text())
            assert cls.expected['classification'] == 'evaluator-only'
            assert cls.expected['marker'] not in json.dumps(cls.inputs)

    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AdoptedIntentWorldCases))
    status = 'passed' if result.wasSuccessful() and result.testsRun == 3 and not result.skipped else 'failed'
    report = {'schema_version':1,'fixture_id':chosen['fixture_id'],'components':chosen['components'],
        'selection_mode':mode,'original_fixture_id':chosen['original_fixture_id'],
        'original_consumer_preserved_sha256':sha(original),'tests_run':result.testsRun,
        'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        'failed':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'status':status,'provider_calls':0,'user_saves_opened':False,'alpha_qualified':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    args.output.with_suffix('.txt').write_text(log.getvalue())
    print(json.dumps(report))
    return 0 if status == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
