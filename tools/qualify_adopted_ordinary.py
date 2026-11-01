"""Qualify Catalog-authored ordinary cases at a new explicit component selection.

Original fixture identities and the copied original consumer remain unchanged.
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

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--engine',type=Path)
    parser.add_argument('--app',type=Path)
    parser.add_argument('--catalog',type=Path)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    selection=json.loads(args.selection.read_text())
    assert selection['fixture_id'] in {'coordinator-adopted-ordinary-3.4.4-1','coordinator-adopted-ordinary-3.4.5-1','coordinator-adopted-ordinary-3.4.6-1','coordinator-adopted-ordinary-3.4.7-1','coordinator-adopted-ordinary-3.4.8-1','coordinator-adopted-ordinary-3.4.9-1'}
    if args.source_root:
        root=args.source_root.resolve()
        for key in ['engine','app','catalog']:
            assert json.loads((root/'COMPONENTS.json').read_text())[key]['commit']==selection['components'][key]
        subprocess.run([sys.executable,'-B',str(root/'tools/verify_development.py')],cwd=root,check=True,stdout=subprocess.DEVNULL)
        engine=root/'IRGS_3_3';app=root/'IRGS_Web';catalog=root/'IRGS_Catalog'
        mode='joined_or_clean_extracted_source'
    else:
        assert all([args.engine,args.app,args.catalog])
        roots={key:getattr(args,key).resolve() for key in ['engine','app','catalog']}
        for key,root in roots.items():
            assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==selection['components'][key]
            assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
        for key,name in [('engine','Engine'),('catalog','Catalog')]:
            assert subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=roots['app'],text=True).strip()==selection['components'][key]
        engine=roots['engine']/'IRGS_3_3';app=roots['app']/'IRGS_Web';catalog=roots['catalog']/'IRGS_Catalog'
        mode='standalone_exact_clean_components_and_pins'
    original=Path(__file__).parent/'catalog_consumers/test_current_ordinary_cases.py'
    assert digest(original)==selection['consumer_source_sha256']
    fixture=catalog/'evaluation/current_ordinary_communication_v1'
    for name,sha in selection['fixture_files_sha256'].items():
        assert digest(fixture/name)==sha
    spec=importlib.util.spec_from_file_location('catalog_original_ordinary_cases',original)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class AdoptedOrdinaryCases(module.CurrentOrdinaryConsumers):
        __unittest_skip__=False
        __unittest_skip_why__=''
        @classmethod
        def setUpClass(cls):
            os.environ['IRGS_ENGINE_ROOT']=str(engine)
            os.environ['IRGS_CATALOG_ROOT']=str(catalog)
            sys.path[:0]=[str(app),str(engine/'runtime')]
            for name,path in [('server',app),('solo_provider',engine),('openai_proposals',engine)]:
                loaded=importlib.import_module(name)
                assert Path(loaded.__file__).resolve().is_relative_to(path)
                setattr(cls,name,loaded)
            cls.cases=json.loads((fixture/'actor_inputs/cases.json').read_text())
            cls.oracle=json.loads((fixture/'evaluator_only/expectations.json').read_text())
            assert cls.cases['fixture_id']=='irgs-current-ordinary-communication-v1'
            assert cls.oracle['classification']=='evaluator-only'
            assert cls.oracle['marker'] not in json.dumps(cls.cases)
    log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AdoptedOrdinaryCases))
    record={'schema_version':1,'fixture_id':selection['fixture_id'],'components':selection['components'],
        'selection_mode':mode,'original_catalog_fixture':'irgs-current-ordinary-communication-v1',
        'original_consumer_preserved_sha256':digest(original),'tests_run':result.testsRun,
        'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        'failed':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'status':'passed' if result.wasSuccessful() and result.testsRun==2 and not result.skipped else 'failed',
        'provider_calls':0,'user_saves_opened':False,'alpha_qualified':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+'\n')
    args.output.with_suffix('.txt').write_text(log.getvalue())
    print(json.dumps(record))
    return 0 if record['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
