"""Regression of existing selected material accounting, not building allowance."""
import copy
import unittest

from core_world import CoreWorld
from historical_campaigns import historical_entry
from r9_runtime import observe
from scene_actions import execute_scene_action
from settlement_runtime import _free, execute
from settlement_setup import initialize, preview
from test_settlement import choices
import world_draft


class ExistingMaterialReservationTests(unittest.TestCase):
    def new_rise(self, *, sibling=False):
        selected = choices()
        selected['permission'] = 'held'
        if sibling:
            selected['company'] = 'sibling'
        return initialize(selected, preview(selected)['review_digest'], 'synthetic-reservation')

    def act(self, world, action, request):
        return execute(world, request, 'founder', action, 'synthetic-explicit-instruction')

    def test_selected_build_pause_resume_and_completion_conserve_existing_stock(self):
        world = self.new_rise()
        self.assertEqual(_free(world.s, 'founder-home', 'grain'), 10)
        # Oren's selected repair reserves only Oren's inputs.
        self.assertEqual(_free(world.s, 'oren-home', 'timber'), 2)
        self.assertEqual(_free(world.s, 'oren-home', 'axe'), 0)
        self.assertEqual(_free(world.s, 'founder-home', 'timber'), 6)
        self.act(world, 'walk_clearing', 'walk')
        self.act(world, 'found', 'found')
        event = {'id': 'settlement:probe', 'at': world.s['clock'] + 1,
            'op': 'execute_settlement_action',
            'params': {'campaign_id': world.s['campaign_id'], 'actor': 'founder',
                'action': 'build', 'request_id': 'probe', 'source_ref': 'synthetic',
                'instruction_ref': 'synthetic'}}
        before_probe = world.save()
        certificate = observe(world.s, event)
        self.assertEqual(world.save(), before_probe)
        reads = {'/'.join(path) for path in certificate['reads']}
        self.assertTrue(any('projects' in path for path in reads))
        self.assertTrue(any('stocks/founder-home' in path for path in reads))
        self.act(world, 'build', 'build')
        original_event = copy.deepcopy(world.s['journal'][-1])
        opening = copy.deepcopy(world.s['stocks']['founder-home'])
        self.assertEqual(opening['timber'], 6)
        self.assertEqual(_free(world.s, 'founder-home', 'timber'), 3)
        self.assertEqual(_free(world.s, 'founder-home', 'axe'), 0)
        self.act(world, 'pause', 'pause')
        self.assertEqual(world.s['stocks']['founder-home'], opening)
        self.assertEqual(_free(world.s, 'founder-home', 'timber'), 6)
        self.assertEqual(_free(world.s, 'founder-home', 'axe'), 1)
        self.act(world, 'resume', 'resume')
        self.assertEqual(_free(world.s, 'founder-home', 'timber'), 3)
        self.act(world, 'wait_hour', 'wait-1')
        self.act(world, 'wait_hour', 'wait-2')
        self.assertEqual(world.s['projects']['shelter']['status'], 'complete')
        self.assertEqual(world.s['stocks']['founder-home']['timber'], 3)
        self.assertEqual(_free(world.s, 'founder-home', 'timber'), 3)
        self.assertEqual(_free(world.s, 'founder-home', 'axe'), 1)
        world = CoreWorld.load(world.save())
        saved = world.save()
        self.assertFalse(world.apply(original_event['id'], original_event['at'],
                                     original_event['op'], **original_event['params']))
        self.assertEqual(world.save(), saved)

    def test_delegated_active_work_reserves_the_same_household_inputs(self):
        world = self.new_rise(sibling=True)
        self.act(world, 'walk_clearing', 'walk')
        self.act(world, 'found', 'found')
        self.act(world, 'delegate', 'delegate')
        self.assertEqual(world.s['projects']['shelter']['worker'], 'rowan')
        self.assertEqual(world.s['stocks']['founder-home']['timber'], 6)
        self.assertEqual(_free(world.s, 'founder-home', 'timber'), 3)
        self.act(world, 'pause', 'pause')
        self.assertEqual(_free(world.s, 'founder-home', 'timber'), 6)
        self.assertEqual(world.s['stocks']['founder-home']['timber'], 6)

    def test_non_rise_selected_scene_stays_independent(self):
        draft = {'schema_version': world_draft.SCHEMA_VERSION, 'draft_id': 'quay-material-regression',
                 'classification': 'mixed', 'profile_id': 'historical-quay',
                 'choices': {'snapshot_sha256': historical_entry('hyw-1415')['snapshot_sha256'],
                     'character': {'kind': 'new', 'name': 'Synthetic courier',
                                   'species': 'human', 'opening_id': 'quay-contact-v1'}}}
        review = world_draft.validate(draft)
        world = world_draft.initialize(draft, draft_digest=review['draft_digest'],
            review_digest=review['review_digest'], campaign_id='synthetic-quay-reservation',
            explicitly_accepted=True)
        actor = world.s['player_actor_ids'][0]
        stock, calendar = copy.deepcopy(world.s['stocks']), copy.deepcopy(world.s['campaign_time'])
        result = execute_scene_action(world, 'quay-gate', actor,
            {'kind': 'scene_action', 'action_id': 'quay-shortcut'}, 'explicit synthetic attempt')
        self.assertEqual(result['status'], 'completed_unsuccessfully')
        self.assertEqual(world.s['elapsed_time']['seconds'], 30)
        self.assertEqual(world.s['stocks'], stock)
        self.assertEqual(world.s['campaign_time'], calendar)
        self.assertNotIn('settlement_model', world.s)
        self.assertEqual(CoreWorld.load(world.save()).s['stocks'], stock)


if __name__ == '__main__':
    unittest.main()
