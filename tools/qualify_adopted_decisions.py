"""Qualify an exact adopted set without rewriting original Catalog guards.

Unchanged Catalog invitation/consequence/draft test methods run in a separately
bound subclass. A new coordinator-authored quay journey adds ordinary creation,
refusal, conserved delivery, original receipt recovery and a real restore fence.
"""
import argparse
import copy
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
from urllib.parse import urlencode


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec);sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path)
    for name in ('engine','app','catalog'): parser.add_argument('--'+name,type=Path)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args();selected = json.loads(args.selection.read_text())
    assert selected['fixture_id'] in {'coordinator-adopted-decisions-3.4.7-1','coordinator-adopted-decisions-3.4.8-1','coordinator-adopted-decisions-3.4.9-1'}
    if args.source_root:
        root = args.source_root.resolve();components = json.loads((root/'COMPONENTS.json').read_text())
        assert all(components[k]['commit'] == selected['components'][k] for k in ('engine','app','catalog'))
        subprocess.run([sys.executable,'-B',str(root/'tools/verify_development.py')],cwd=root,check=True,stdout=subprocess.DEVNULL)
        engine,app,catalog = root/'IRGS_3_3',root/'IRGS_Web',root/'IRGS_Catalog'
        mode = 'joined_or_clean_extracted_source'
    else:
        assert args.engine and args.app and args.catalog
        roots = {k:getattr(args,k).resolve() for k in ('engine','app','catalog')}
        for k,path in roots.items():
            assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip() == selected['components'][k]
            assert not subprocess.check_output(['git','status','--porcelain'],cwd=path).strip()
        for k,name in [('engine','Engine'),('catalog','Catalog')]:
            assert subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=roots['app'],text=True).strip() == selected['components'][k]
        engine,app,catalog = roots['engine']/'IRGS_3_3',roots['app']/'IRGS_Web',roots['catalog']/'IRGS_Catalog'
        mode = 'standalone_exact_clean_sources_and_pins'
    root = Path(__file__).resolve().parent.parent
    original = root/'tools/catalog_consumers'
    for name,digest in selected['original_consumers_sha256'].items(): assert sha(original/name) == digest
    for name,digest in selected['catalog_fixture_files_sha256'].items(): assert sha(catalog/name) == digest
    extension = root/'provenance/qa/decisions_3_4_7'
    for name,digest in selected['quay_extension_files_sha256'].items(): assert sha(extension/name) == digest
    actor_inputs = json.loads((extension/'actor_inputs.json').read_text())
    oracle = json.loads((extension/'evaluator_only.json').read_text())
    assert oracle['classification'] == 'evaluator-only' and oracle['marker'] not in json.dumps(actor_inputs)
    os.environ['IRGS_ENGINE_ROOT'],os.environ['IRGS_CATALOG_ROOT'] = str(engine),str(catalog)
    sys.path[:0] = [str(app),str(engine/'runtime'),str(catalog),str(root)]
    import tools.tests
    modules = [
        ('test_current_ordinary_consumers','test_current_ordinary_cases.py'),
        ('test_intent_world_draft_consumers','test_intent_world_draft_cases.py'),
        ('test_adopted_consequences_consumers','test_adopted_consequences_cases.py'),
        ('test_invitation_decision_consumers','test_invitation_decision_cases.py')]
    for name,file in modules:
        module = load('tools.tests.'+name,original/file)
        setattr(tools.tests,name,module)
    original_invitation = module
    import adopted_consequences_evaluation
    adopted_consequences_evaluation.load_fixture(catalog)

    class AdoptedDecisionCases(original_invitation.InvitationDecisionConsumers):
        __unittest_skip__ = False
        __unittest_skip_why__ = ''

        @classmethod
        def setUpClass(cls):
            for name,path in [('server',app),('solo_provider',engine),('openai_proposals',engine),('world_draft',engine),('offline_responses',engine),('core_world',engine)]:
                imported = importlib.import_module(name)
                assert Path(imported.__file__).resolve().is_relative_to(path)
                setattr(cls,name,imported)
            ordinary = catalog/'evaluation/current_ordinary_communication_v1'
            invitation = catalog/'evaluation/invitation_decision_v1'
            cls.cases = json.loads((ordinary/'actor_inputs/cases.json').read_text())
            cls.oracle = json.loads((ordinary/'evaluator_only/expectations.json').read_text())
            cls.inputs = json.loads((invitation/'actor_inputs/cases.json').read_text())
            cls.new_oracle = json.loads((invitation/'evaluator_only/expectations.json').read_text())
            cls.expected = json.loads((catalog/'evaluation/adopted_consequences_v1/evaluator_only/expectations.json').read_text())
            assert cls.new_oracle['marker'] not in json.dumps(cls.inputs)

        def test_ordinary_quay_decision_delivery_restart_and_restore(self):
            entry = self.ok('/api/historical-entry/hyw-1415')
            self.assertEqual(entry['snapshot_sha256'],actor_inputs['snapshot_sha256'])
            fields = {'profile_id':'military','scenario_id':'hundred-years-war','entry_id':'hyw-1415','snapshot_sha256':actor_inputs['snapshot_sha256']}
            options = self.ok('/api/starting-options?'+urlencode(fields))
            opening = actor_inputs['opening_id']
            self.assertTrue(next(row for row in options['playable_openings'] if row['id']==opening)['fictional'])
            preview = self.ok('/api/starting-preview?'+urlencode({**fields,'selection_digest':options['selection_digest'],'starting_scenario_id':'individual','character_kind':'new','species':'human','opening_id':opening}))
            self.assertEqual(preview['status'],'supported_slice')
            body = {**fields,'name':'Independent selected decision','selection_digest':options['selection_digest'],'request_id':'independent-quay-decision-create','character':{'kind':'new','name':actor_inputs['character_name'],'species':'human','background':'','opening_id':opening}}
            self.assertFalse(list(self.store.folder.glob('*.json')))
            key = self.ok('/api/create',body)['id'];checkpoint = self.store.path(key).read_bytes();revision = self.store.read(key)['revision']
            self.assertEqual(self.ok('/api/create',body)['id'],key);self.assertEqual(self.store.path(key).read_bytes(),checkpoint)
            actor = self.view(key)['actor_id'];initial = copy.deepcopy(self.store.read(key)['state'])
            request,refusal = self.reviewed_action(key,actor,actor_inputs['request'],100)
            self.assertIn(oracle['refusal'],refusal['outcome']['summary'].lower())
            state = self.store.read(key)['state'];self.assertEqual(state['stocks'],initial['stocks'])
            self.assertEqual(state['elapsed_time']['seconds'],oracle['elapsed_after_request'])
            self.assertEqual(state['campaign_time'],initial['campaign_time'])
            self.assertNotIn('FICTIONAL-QUAY-CONTACT',state['player_actor_ids'])
            for index,action in enumerate(actor_inputs['continuation'],101): self.reviewed_action(key,actor,action,index)
            state = self.store.read(key)['state']
            self.assertEqual(state['stocks'][actor]['sealed_dispatch'],oracle['actor_dispatch'])
            self.assertEqual(state['stocks']['clerk-tray']['sealed_dispatch'],oracle['desk_dispatch'])
            self.assertEqual(sum(row.get('sealed_dispatch',0) for row in state['stocks'].values()),1)
            self.assertEqual(state['elapsed_time']['seconds'],oracle['elapsed_after_delivery'])
            self.assertEqual(state['campaign_time'],initial['campaign_time'])
            saved = self.store.path(key).read_bytes();self.stop();self.start()
            self.assertEqual(self.http('/api/intent/execute',{**request,'explicitly_accepted':True}),(200,refusal))
            self.assertEqual(self.store.path(key).read_bytes(),saved)
            self.assertNotIn(oracle['marker'],json.dumps(self.view(key)))
            self.store.path(key).write_bytes(checkpoint)  # Explicit older synthetic checkpoint, never a user save.
            self.ok('/api/delete',{'id':key,'revision':revision});self.ok('/api/restore',{'id':key,'revision':revision})
            self.assertEqual(self.http('/api/intent/execute',{**request,'explicitly_accepted':True})[0],400)
            self.assertEqual(self.store.path(key).read_bytes(),checkpoint)

    log = io.StringIO();result = unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AdoptedDecisionCases))
    status = 'passed' if result.wasSuccessful() and result.testsRun==4 and not result.skipped else 'failed'
    report = {'schema_version':1,'fixture_id':selected['fixture_id'],'components':selected['components'],'selection_mode':mode,'status':status,'tests_run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),'failed':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'original_catalog_consumers_preserved':True,'coordinator_extension':'ordinary quay refusal/conserved delivery/restart/restore','provider_calls':0,'user_saves_opened':False,'alpha_qualified':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');args.output.with_suffix('.txt').write_text(log.getvalue());print(json.dumps(report))
    return 0 if status=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
