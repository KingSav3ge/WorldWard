"""User-adopted quay-deadline-v1: an authored delivery deadline that closes delivery.

See engine/NEEDS_AND_RELIEF_RULES.md. Fictional scenario rule, not history.
"""
import unittest
from campaign_library import initial_campaign
from core_world import CoreWorld
from historical_campaigns import historical_entry
from starting_selection import initialize_player, options_for_world
from scene_actions import execute_scene_action
from scene_setup import DEADLINE_OPENING, DEADLINE_SECONDS


class QuayDeadlineTests(unittest.TestCase):
    def create(self, opening=DEADLINE_OPENING):
        preview = historical_entry('hyw-1415')
        world = initial_campaign('military', 'synthetic-deadline', scenario_id='hundred-years-war',
                                 entry_id='hyw-1415', snapshot_sha256=preview['snapshot_sha256'])
        options = options_for_world(world)
        character = {'kind': 'new', 'name': 'Synthetic courier', 'species': 'human', 'opening_id': opening}
        world = initialize_player(world, character, selection_digest=options['selection_digest'],
                                  request_ref='explicit-synthetic-opening-review')
        return world, world.s['player_actor_ids'][0]

    def run_actions(self, world, actor, keys):
        results = []
        for index, key in enumerate(keys):
            results.append(execute_scene_action(world, f'synthetic:{world.s["clock"]}:{index}:{key}', actor,
                {'kind': 'scene_action', 'action_id': key}, 'explicit-synthetic-' + key))
        return results

    def test_variant_is_reviewed_and_existing_openings_keep_their_order(self):
        openings = options_for_world(initial_campaign('military', 'x', scenario_id='hundred-years-war',
            entry_id='hyw-1415', snapshot_sha256=historical_entry('hyw-1415')['snapshot_sha256']))['playable_openings']
        self.assertEqual([o['id'] for o in openings],
                         ['quay-delivery-v1', 'quay-contact-v1', 'quay-contact-decision-v1', DEADLINE_OPENING])
        review = openings[-1]['review']
        self.assertIn(f'within {DEADLINE_SECONDS} authored seconds', review)

    def test_delivery_within_the_deadline_succeeds(self):
        world, actor = self.create()
        results = self.run_actions(world, actor, ['look-quay', 'quay-shortcut', 'quay-passage',
                                                  'passage-desk', 'deliver-dispatch'])
        self.assertEqual(results[-1]['status'], 'completed_successfully')
        self.assertEqual(world.s['elapsed_time']['seconds'], 150)
        self.assertEqual(world.s['stocks'][actor]['sealed_dispatch'], 0)

    def test_late_delivery_fails_keeps_dispatch_and_stays_closed_after_reload(self):
        world, actor = self.create()
        # 45 + 45 + 20 + 20 + 20 + 20 = 170; the 10-second hand-over would end at 180 (allowed),
        # so one more look makes it end at 200.
        self.run_actions(world, actor, ['quay-passage', 'passage-desk', 'look-desk', 'look-desk',
                                        'look-desk', 'look-desk', 'look-desk'])
        self.assertEqual(world.s['elapsed_time']['seconds'], 190)
        [late] = self.run_actions(world, actor, ['deliver-dispatch'])
        self.assertEqual(late['status'], 'completed_unsuccessfully')
        self.assertEqual(world.s['elapsed_time']['seconds'], 200, 'the attempt still takes its time')
        self.assertEqual(world.s['stocks'][actor]['sealed_dispatch'], 1)
        self.assertEqual(world.s['stocks']['clerk-tray'].get('sealed_dispatch', 0), 0)
        reloaded = CoreWorld.load(world.save())
        [again] = self.run_actions(reloaded, actor, ['deliver-dispatch'])
        self.assertEqual(again['status'], 'completed_unsuccessfully')
        self.assertEqual(reloaded.s['stocks'][actor]['sealed_dispatch'], 1)

    def test_handover_ending_exactly_at_the_deadline_is_accepted(self):
        world, actor = self.create()
        self.run_actions(world, actor, ['quay-passage', 'passage-desk', 'look-desk', 'look-desk',
                                        'look-desk', 'look-desk'])
        self.assertEqual(world.s['elapsed_time']['seconds'], 170)
        [result] = self.run_actions(world, actor, ['deliver-dispatch'])
        self.assertEqual(result['status'], 'completed_successfully')

    def test_original_opening_has_no_deadline(self):
        world, actor = self.create('quay-delivery-v1')
        self.run_actions(world, actor, ['quay-passage', 'passage-desk'] + ['look-desk'] * 8)
        [result] = self.run_actions(world, actor, ['deliver-dispatch'])
        self.assertEqual(result['status'], 'completed_successfully')


if __name__ == '__main__':
    unittest.main()
