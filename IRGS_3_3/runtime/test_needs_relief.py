"""User-adopted rise-needs-1: hunger, fatigue, steward relief and upkeep obligation.

See engine/NEEDS_AND_RELIEF_RULES.md. Fictional, uncalibrated rules.
"""
import unittest
from core_world import CoreWorld
from irgs_reference import InvalidEvent
from settlement_setup import initialize, preview, NEEDS_PROFILE
from settlement_runtime import execute


def choices(**overrides):
    c = dict(template_id='R00', founder_name='Ari', household_name='Ari household',
             settlement_name='Willow Camp', region_name='Greywater Reach', date_label='Spring, Year 1',
             company='solo', permission='held', supplies='basic')
    c.update(overrides)
    return c


class NeedsReliefTests(unittest.TestCase):
    def world(self, **overrides):
        c = choices(**overrides)
        return initialize(c, preview(c)['review_digest'], 'needs-fixture')

    def act(self, w, action):
        return execute(w, f'action-{w.s["clock"] + 1}', 'founder', action, 'explicit-fixture-request')

    def rejected(self, w, action):
        before = w.save()
        with self.assertRaises(InvalidEvent):
            self.act(w, action)
        self.assertEqual(w.save(), before, 'a rejected attempt commits nothing')

    def last_text(self, w):
        records = w.s['settlement_receipts']['founder']
        return [r['text'] for k, r in records.items() if not k.endswith(':inspection')][-1]

    def until_shortfall(self, w, household='founder-home'):
        seen = {k for k, a in w.s['provision']['assessments'].items() if a['deficit'] > 0}
        for _ in range(200):
            self.act(w, 'wait_hour')
            fresh = {k for k, a in w.s['provision']['assessments'].items()
                     if a['deficit'] > 0 and a['household'] == household} - seen
            if fresh:
                return
        self.fail('no shortfall occurred')

    def test_without_profile_behaviour_and_review_are_unchanged(self):
        c = choices()
        review = preview(c)
        self.assertNotIn('needs_setup', review)
        w = self.world()
        self.assertNotIn('needs', w.s)
        self.assertNotIn('steward-store', w.s['stocks'])
        for action in ('feed_household', 'rest', 'request_relief'):
            self.rejected(w, action)
        with self.assertRaises(ValueError):
            preview(choices(needs_profile='rise-needs-0'))

    def test_profile_is_reviewed_and_relief_store_is_conserved_existing_stock(self):
        review = preview(choices(needs_profile=NEEDS_PROFILE))
        self.assertEqual(review['needs_setup']['id'], NEEDS_PROFILE)
        self.assertNotEqual(review['review_digest'], preview(choices())['review_digest'])
        w = self.world(needs_profile=NEEDS_PROFILE)
        self.assertEqual(w.s['stocks']['steward-store'], {'grain': 8})
        self.assertEqual(w.s['opening_stock']['grain'], 12 + 4 + 8)
        self.assertEqual(set(w.s['needs']), {'founder', 'oren'})

    def test_hunger_blocks_work_relief_is_lent_once_and_feeding_restores(self):
        w = self.world(needs_profile=NEEDS_PROFILE)
        self.act(w, 'request_relief')  # Elin's recorded refusal: there is no shortfall yet
        self.assertIn('only after a recorded provision shortfall', self.last_text(w))
        self.assertEqual(w.s['stocks']['steward-store']['grain'], 8)
        self.until_shortfall(w)
        self.assertTrue(w.s['needs']['founder']['hungry'])
        self.assertEqual(w.s['stocks']['founder-home']['grain'], 2, 'seed grain is protected')
        self.rejected(w, 'feed_household')  # only seed grain remains
        self.act(w, 'request_relief')
        self.assertEqual(w.s['stocks']['founder-home']['grain'], 4)
        self.assertEqual(w.s['stocks']['steward-store']['grain'], 6)
        [obligation] = w.s['relief_obligations'].values()
        self.assertEqual((obligation['owed_seconds'], obligation['status']), (3600, 'open'))
        self.act(w, 'request_relief')
        self.assertIn('already given relief', self.last_text(w))
        self.assertEqual(w.s['stocks']['steward-store']['grain'], 6)
        self.act(w, 'walk_clearing'); self.act(w, 'found')
        self.rejected(w, 'build')  # hungry people cannot start work
        self.act(w, 'feed_household')
        self.assertFalse(w.s['needs']['founder']['hungry'])
        self.assertEqual(w.s['stocks']['founder-home']['grain'], 3)
        w2 = CoreWorld.load(w.save())
        self.assertEqual(w2.s, w.s, 'needs and obligations persist across save and load')

    def test_upkeep_discharges_obligation_and_fatigue_holds_work_until_rest(self):
        w = self.world(needs_profile=NEEDS_PROFILE, company='sibling')
        self.act(w, 'walk_clearing'); self.act(w, 'found'); self.act(w, 'build')
        while w.s['projects']['shelter']['status'] == 'active':
            self.act(w, 'wait_hour')  # returns early at Oren's repair boundary
        self.assertEqual(w.s['projects']['shelter']['status'], 'complete')
        self.assertEqual(w.s['needs']['founder']['worked_since_rest'], 3600)

        def relief_and_feed():
            self.until_shortfall(w)
            self.act(w, 'walk_commons'); self.act(w, 'request_relief'); self.act(w, 'walk_clearing')
            self.act(w, 'feed_household')
            self.assertFalse(w.s['needs']['founder']['hungry'] or w.s['needs']['rowan']['hungry'])

        relief_and_feed()
        first = next(k for k, o in w.s['relief_obligations'].items() if o['status'] == 'open')
        self.assertEqual(w.s['relief_obligations'][first]['owed_seconds'], 7200, '4 portions owe 2 hours')
        for _ in range(2):
            self.act(w, 'path_upkeep')
            while any(p['status'] == 'active' for p in w.s['projects'].values() if p['kind'] == 'upkeep'):
                self.act(w, 'wait_hour')
        self.assertEqual(w.s['relief_obligations'][first]['status'], 'discharged')
        self.assertEqual(w.s['needs']['founder']['worked_since_rest'], 3 * 3600)
        self.rejected(w, 'path_upkeep')  # nothing is owed

        relief_and_feed()
        self.act(w, 'path_upkeep')
        while any(p['status'] == 'active' for p in w.s['projects'].values() if p['kind'] == 'upkeep'):
            self.act(w, 'wait_hour')
        held = [p for p in w.s['projects'].values() if p['kind'] == 'upkeep' and p['status'] == 'held']
        self.assertEqual(len(held), 0, 'a full hour completes exactly at the 4-hour limit')
        self.assertEqual(w.s['needs']['founder']['worked_since_rest'], 14400)
        self.rejected(w, 'path_upkeep')  # tired
        self.act(w, 'rest')
        self.assertIn('rest for 2 hours in your shelter', self.last_text(w))
        self.assertEqual(w.s['needs']['founder']['worked_since_rest'], 0)
        if w.s['needs']['founder']['hungry']:
            self.act(w, 'feed_household')
        self.act(w, 'path_upkeep')
        while any(p['status'] == 'active' for p in w.s['projects'].values() if p['kind'] == 'upkeep'):
            self.act(w, 'wait_hour')
        self.assertFalse(any(o['status'] == 'open' for o in w.s['relief_obligations'].values()))

    def test_no_relief_decision_when_elin_is_player_controlled(self):
        w = self.world(needs_profile=NEEDS_PROFILE)
        self.until_shortfall(w)
        w.s['player_actor_ids'].append('elin')  # synthetic changed-control fixture
        w = CoreWorld.load(w.save())
        self.rejected(w, 'request_relief')
        self.assertEqual(w.s['stocks']['steward-store']['grain'], 8)
        self.assertEqual(w.s['relief_obligations'], {})

    def test_fatigue_holds_a_project_mid_hour_and_rest_lets_it_resume(self):
        w = self.world(needs_profile=NEEDS_PROFILE)
        w.s['needs']['founder']['worked_since_rest'] = 14400 - 600  # direct fixture state
        self.act(w, 'walk_clearing'); self.act(w, 'found'); self.act(w, 'build')
        self.act(w, 'wait_hour')
        shelter = w.s['projects']['shelter']
        self.assertEqual((shelter['status'], shelter['worked']), ('held', 600))
        self.act(w, 'pause')
        self.rejected(w, 'resume')
        self.act(w, 'rest')
        self.assertIn('rest for 4 hours without shelter', self.last_text(w))
        self.act(w, 'resume')
        self.assertEqual(w.s['projects']['shelter']['status'], 'active')


if __name__ == '__main__':
    unittest.main()
