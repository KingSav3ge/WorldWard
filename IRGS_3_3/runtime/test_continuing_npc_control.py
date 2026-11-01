"""Selected R00 decision safety and continuing play over existing intent contracts."""
import copy
import json
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from core_world import CoreWorld
from historical_campaigns import historical_entry
from runtime_contracts import AcceptedIntent, WorldScope
from scene_actions import execute_scene_action
import shared_runtime as shared
import supported_intent as intent
from test_settlement import choices
from test_solo_provider import AtomicTestHost
from test_temporal_registry import entity, policy, validate_registry
import world_draft


class ContinuingNpcControlTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='irgs-oren-continuation-')
        self.addCleanup(temporary.cleanup)
        for target in ('solo_provider.CapabilityBroker.dispatch',
                       'openai_proposals.OpenAIProposalTransport.__call__', 'socket.socket.connect'):
            guard = patch(target, side_effect=AssertionError('No provider or network'))
            guard.start()
            self.addCleanup(guard.stop)
        selected = choices()
        selected['permission'] = 'held'
        draft = {'schema_version': world_draft.SCHEMA_VERSION, 'draft_id': 'continuation-rise',
                 'classification': 'fictional', 'profile_id': 'rise-r00', 'choices': selected}
        reviewed = world_draft.validate(draft)
        self.world = world_draft.initialize(draft, draft_digest=reviewed['draft_digest'],
            review_digest=reviewed['review_digest'], campaign_id='synthetic-continuing-rise',
            explicitly_accepted=True)
        self.host = AtomicTestHost(temporary.name, self.world)

    def scope(self):
        return WorldScope(self.world.s['campaign_id'], 'branch-1', self.host.restore_id, self.world.checksum())

    def prepare(self, action, request_id, words):
        capability = next(c for c in shared.capabilities(self.world, 'founder')
                          if json.loads(c.action_json).get('action_id') == action)
        args = dict(actor_id='founder', intention=words, capability_id=capability.capability_id,
                    branch_id='branch-1', restore_id=self.host.restore_id)
        before = self.world.save()
        reviewed = intent.review(self.world, **args)
        self.assertEqual(reviewed['status'], 'supported')
        self.assertFalse(reviewed['committed'])
        request = intent.prepare(self.world, request_id=request_id, review_id=reviewed['review_id'], **args)
        self.assertEqual(self.world.save(), before)
        return request

    def submit(self, request):
        return intent.execute(self.world, request, current_scope=self.scope(), persist=self.host.persist,
                              explicitly_accepted=True)

    def act(self, action, request_id):
        request = self.prepare(action, request_id, 'Exact selected attempt: ' + action)
        return request, self.submit(request)

    def camp_and_return(self):
        for action in ('walk_clearing', 'found', 'walk_commons'):
            self.act(action, action)

    def agree(self):
        self.camp_and_return()
        self.act('wait_hour', 'finish-repair')
        return self.act('invite', 'invite-agree')

    def test_normal_refusal_later_agreement_departure_arrival_and_restore(self):
        self.camp_and_return()
        self.assertNotEqual(self.world.s['projects']['oren-repair']['status'], 'complete')
        earlier, refusal = self.act('invite', 'invite-early')
        self.assertIn('declines to move', json.dumps(refusal).lower())
        self.assertNotIn('oren-move', self.world.s['migrations'])
        self.act('wait_hour', 'finish-repair')
        self.assertEqual(self.world.s['projects']['oren-repair']['status'], 'complete')
        agreement_request, agreement = self.act('invite', 'invite-agree')
        self.assertIn('agrees to move', json.dumps(agreement).lower())
        self.assertEqual(self.world.s['migrations']['oren-move']['status'], 'agreed')
        self.assertEqual(self.world.s['actors']['oren']['current']['location'], 'commons')
        checkpoint = self.world.save()
        stock = copy.deepcopy(self.world.s['stocks'])
        calendar = copy.deepcopy(self.world.s['campaign_time'])
        departure_request, departure = self.act('arrange_departure', 'departure')
        self.assertEqual(self.world.s['migrations']['oren-move']['status'], 'transit')
        self.assertEqual(self.world.s['households']['oren-home']['settlement'], None)
        self.act('wait_hour', 'arrival')
        self.assertEqual(self.world.s['migrations']['oren-move']['status'], 'arrived')
        self.assertEqual(self.world.s['actors']['oren']['current']['location'], 'clearing')
        self.assertEqual(self.world.s['households']['oren-home']['settlement'], 'camp')
        self.assertEqual(self.world.s['stocks'], stock)
        self.assertEqual(self.world.s['campaign_time'], calendar)
        self.world = self.host.load()
        saved, writes = self.world.save(), self.host.writes
        for request, original in ((earlier, refusal), (agreement_request, agreement),
                                  (departure_request, departure)):
            self.assertEqual(self.submit(AcceptedIntent.from_json(request.to_json())), original)
        self.assertEqual(self.world.save(), saved)
        self.assertEqual(self.host.writes, writes)
        public = json.dumps(shared.actor_view(self.world, 'founder', branch_id='branch-1',
                                             restore_id=self.host.restore_id))
        self.assertNotIn('seed_reserve', public)
        # Restore a genuine earlier synthetic checkpoint, discarding the departure.
        self.host.restore_id = 'restore-2'
        self.world = CoreWorld.load(checkpoint)
        self.host.install(self.world)
        before = self.world.save()
        with self.assertRaises(shared.SharedActionUnavailable) as err:
            self.submit(departure_request)
        self.assertEqual(err.exception.code, 'stale_scope')
        self.assertEqual(self.world.save(), before)
        self.act('arrange_departure', 'fresh-departure')
        self.act('wait_hour', 'fresh-arrival')
        self.assertEqual(self.world.s['migrations']['oren-move']['status'], 'arrived')
        self.assertEqual(self.world.s['stocks'], stock)

    def test_no_new_npc_decision_if_target_is_player_controlled(self):
        self.camp_and_return()
        # Synthetic control change tests a safety boundary; ordinary R00 starts
        # with only the founder controlled and does not select this situation.
        before_menu = [c.public() for c in shared.capabilities(self.world, 'founder')]
        self.world.s['player_actor_ids'].append('oren')
        self.host.install(self.world)
        self.assertEqual([c.public() for c in shared.capabilities(self.world, 'founder')], before_menu)
        request = self.prepare('invite', 'not-an-npc', 'Would you move?')
        before, writes = self.world.save(), self.host.writes
        unchanged = {key: copy.deepcopy(self.world.s[key]) for key in
                     ('settlement_receipts', 'elapsed_time', 'campaign_time', 'stocks')}
        with self.assertRaises(shared.SharedActionUnavailable) as err:
            self.submit(request)
        self.assertEqual(err.exception.code, 'action_unavailable')
        self.assertEqual(self.world.save(), before)
        self.assertEqual(self.host.writes, writes)
        for key, value in unchanged.items():
            self.assertEqual(self.world.s[key], value, key)
        self.assertNotIn('oren-move', self.world.s['migrations'])
        self.assertNotIn('shared:not-an-npc:invitation',
                         self.world.s['settlement_receipts'].get('oren', {}))

    def test_earlier_agreement_does_not_direct_now_controlled_person(self):
        original_request, original = self.agree()
        self.world.s['player_actor_ids'].append('oren')
        self.host.install(self.world)
        before_replay, writes = self.world.save(), self.host.writes
        self.assertEqual(self.submit(original_request), original)
        self.assertEqual(self.world.save(), before_replay)
        self.assertEqual(self.host.writes, writes)
        request = self.prepare('arrange_departure', 'controlled-departure', 'Arrange departure.')
        before, writes = self.world.save(), self.host.writes
        with self.assertRaises(shared.SharedActionUnavailable) as err:
            self.submit(request)
        self.assertEqual(err.exception.code, 'action_unavailable')
        self.assertEqual(self.world.save(), before)
        self.assertEqual(self.host.writes, writes)
        self.assertEqual(self.world.s['migrations']['oren-move']['status'], 'agreed')
        self.assertIn('agrees to move', json.dumps(original).lower())

    def test_temporally_absent_contact_cannot_make_a_new_decision(self):
        self.camp_and_return()
        # Explicit synthetic current-existence fixture, not an ordinary setup rule.
        people = {key: entity(key, 'character', actor['name'], start=0, species=actor['species'])
                  for key, actor in self.world.s['actors'].items()}
        people['oren']['versions'][0]['exists'] = False
        registry = {'schema_version': 1, 'source_mode': 'playthrough',
                    'axis': {'id': 'synthetic-ordinal', 'unit': 'step'}, 'as_of': 0,
                    'entities': people, 'relations': {},
                    'eligibility': {'founder-solo': policy('founder', 'individual', start=0,
                                                           actor_ids=['founder'])},
                    'scenarios': {'individual': {'id': 'individual', 'title': 'Synthetic solo',
                                                  'character_creation_allowed': True}}}
        validate_registry(registry, self.world.s['actors'])
        self.world.s['entity_registry'] = registry
        self.world = CoreWorld(state=self.world.s)
        self.host.install(self.world)
        request = self.prepare('invite', 'absent-contact', 'Would you move?')
        before, writes = self.world.save(), self.host.writes
        with self.assertRaises(shared.SharedActionUnavailable) as err:
            self.submit(request)
        self.assertEqual(err.exception.code, 'action_unavailable')
        self.assertEqual(self.world.save(), before)
        self.assertEqual(self.host.writes, writes)
        self.assertNotIn('oren-move', self.world.s['migrations'])

    def test_non_rise_opening_and_failed_route_are_unchanged(self):
        draft = {'schema_version': world_draft.SCHEMA_VERSION, 'draft_id': 'continuation-quay',
                 'classification': 'mixed', 'profile_id': 'historical-quay',
                 'choices': {'snapshot_sha256': historical_entry('hyw-1415')['snapshot_sha256'],
                     'character': {'kind': 'new', 'name': 'Synthetic courier',
                                   'species': 'human', 'opening_id': 'quay-contact-v1'}}}
        reviewed = world_draft.validate(draft)
        world = world_draft.initialize(draft, draft_digest=reviewed['draft_digest'],
            review_digest=reviewed['review_digest'], campaign_id='synthetic-continuing-quay',
            explicitly_accepted=True)
        actor = world.s['player_actor_ids'][0]
        stock, calendar = copy.deepcopy(world.s['stocks']), copy.deepcopy(world.s['campaign_time'])
        result = execute_scene_action(world, 'synthetic-gate', actor,
            {'kind': 'scene_action', 'action_id': 'quay-shortcut'}, 'explicit synthetic request')
        self.assertEqual(result['status'], 'completed_unsuccessfully')
        self.assertEqual(world.s['elapsed_time']['seconds'], 30)
        self.assertEqual(world.s['stocks'], stock)
        self.assertEqual(world.s['campaign_time'], calendar)
        self.assertNotIn('settlement_model', world.s)


if __name__ == '__main__':
    unittest.main()
