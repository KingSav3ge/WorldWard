"""Authenticated disposable previews over the pinned Engine; synthetic stores only."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Store, make_server
import world_draft


class CreatorPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='worldward-creator-preview-')
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        # Existing ordinary Core save, created only as a synthetic test fixture.
        self.existing = self.store.create('Existing story remains unchanged')
        self.server = make_server(0, self.tmp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.token = self.call('/api/campaigns', creator=False)[1]['token']
        for target in ('solo_provider.CapabilityBroker.dispatch',
                       'openai_proposals.OpenAIProposalTransport.__call__'):
            guard = patch(target, side_effect=AssertionError('Creator preview must remain offline'))
            self.addCleanup(guard.stop)
            guard.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, path, body=None, *, creator=True, token=None, headers=None):
        if creator:
            if body is None:
                path += ('&' if '?' in path else '?') + 'mode=creator'
            else:
                body = {**body, 'mode': 'creator'}
        supplied = {'Content-Type': 'application/json', 'X-IRGS-Token': self.token if token is None and hasattr(self, 'token') else token or ''}
        supplied.update(headers or {})
        request = Request(self.origin + path, headers=supplied,
                          data=None if body is None else json.dumps(body).encode())
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def source_options(self):
        code, packet = self.call('/api/creator/drafts/options')
        self.assertEqual(code, 200, packet)
        self.assertEqual(packet['draft_schema'], world_draft.SCHEMA_VERSION)
        self.assertEqual([row['id'] for row in packet['profiles']], ['rise-r00', 'historical-quay'])
        self.assertTrue(all(row['available'] for row in packet['profiles']))
        return packet

    def draft(self, profile, *, opening='quay-contact-v1'):
        if profile['id'] == 'rise-r00':
            choices = dict(template_id='R00', founder_name='Ari', household_name='Ari household',
                           settlement_name='Willow Camp', region_name='Greywater Reach',
                           date_label='Spring, Year 1', company='solo', permission='seek', supplies='basic')
        else:
            choices = {'snapshot_sha256': profile['snapshot_sha256'],
                       'character': {'kind': 'new', 'name': 'Synthetic courier', 'species': 'human',
                                     'opening_id': opening}}
        return {'schema_version': world_draft.SCHEMA_VERSION, 'draft_id': 'b' * 32,
                'profile_id': profile['id'], 'classification': profile['classification'], 'choices': choices}

    def bytes_snapshot(self):
        root = Path(self.tmp.name)
        return {path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob('*') if path.is_file()}

    def test_real_guards_precede_source_access_and_projection(self):
        before = self.bytes_snapshot()
        cases = [
            {'creator': False}, {'token': 'wrong'},
            {'headers': {'Origin': 'https://example.invalid'}},
            {'headers': {'Host': 'attacker.invalid'}}]
        for args in cases:
            with self.subTest(args=args), patch('creator_preview.options') as options, \
                    patch('creator_preview.preview') as preview:
                self.assertEqual(self.call('/api/creator/drafts/options', **args)[0], 403)
                self.assertEqual(self.call('/api/creator/drafts/preview',
                                          {'draft': {}, 'options_digest': 'untrusted'}, **args)[0], 403)
                options.assert_not_called()
                preview.assert_not_called()
        self.assertEqual(self.bytes_snapshot(), before)

    def test_both_profiles_and_both_quay_openings_use_real_engine_without_writes(self):
        before = self.bytes_snapshot()
        engine_preview = world_draft.preview_initialization
        engine_results = []

        def capture_preview(draft):
            result = engine_preview(draft)
            engine_results.append(json.loads(json.dumps(result)))  # Compare the exact JSON wire DTO.
            return result

        with patch.object(Store, 'write', side_effect=AssertionError('Preview wrote a campaign')), \
                patch('world_draft.preview_initialization', side_effect=capture_preview) as projection:
            packet = self.source_options()
            for profile in packet['profiles']:
                openings = ['quay-contact-v1', 'quay-contact-decision-v1'] if profile['id'] == 'historical-quay' else [None]
                for opening in openings:
                    draft = self.draft(profile, opening=opening)
                    original = copy.deepcopy(draft)
                    with self.subTest(profile=profile['id'], opening=opening):
                        code, result = self.call('/api/creator/drafts/preview',
                                                 {'draft': draft, 'options_digest': packet['options_digest']})
                        self.assertEqual(code, 200, result)
                        self.assertEqual(result, engine_results[-1])
                        self.assertEqual(projection.call_args.args, (draft,))
                        self.assertEqual(draft, original)
                        self.assertEqual(result['status'], 'preview_only')
                        self.assertFalse(result['committed'])
                        self.assertFalse(result['preview_identities_reusable'])
                        self.assertTrue(result['requires_explicit_acceptance'])
                        self.assertTrue(result['actor_view']['actor_id'])
                        self.assertEqual(result['actor_view']['render_usage'],
                                         {'provider_calls': 0, 'model_tokens': 0})
                        if profile['classification'] == 'mixed':
                            self.assertIsNone(result['actor_view']['start_context']['civil_time']['time'])
        self.assertEqual(self.bytes_snapshot(), before)
        self.assertEqual(self.store.read(self.existing['id']), self.existing)

    def test_nested_projection_excludes_private_world_and_other_actor_knowledge(self):
        packet = self.source_options()
        before = self.bytes_snapshot()
        initializer = world_draft.initialize
        marker = 'PRIVATE-CREATOR-WORLD-AND-OTHER-ACTOR'
        selected_actors = []

        def marked_initializer(*args, **kwargs):
            world = initializer(*args, **kwargs)
            selected_actors.append(world.s['player_actor_ids'][0])
            world.s['creator_private_marker'] = marker
            world.s['actors']['private-observer'] = {'id': 'private-observer', 'name': marker,
                                                     'species': 'human', 'current': {}}
            world.s['evidence']['private-creator-note'] = {
                'subject': 'private-observer', 'assertion': marker, 'status': 'testimony',
                'source_ref': marker, 'recorded_at': 0}
            world.s['knowledge']['private-observer'] = {'private-creator-note': {'received_at': 0}}
            return world

        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value))
            return set()

        for profile in packet['profiles']:
            with self.subTest(profile=profile['id']), patch('world_draft.initialize', side_effect=marked_initializer), \
                    patch.object(Store, 'write', side_effect=AssertionError('Preview wrote a campaign')):
                code, result = self.call('/api/creator/drafts/preview',
                                         {'draft': self.draft(profile), 'options_digest': packet['options_digest']})
                self.assertEqual(code, 200, result)
                self.assertEqual(result['actor_view']['actor_id'], selected_actors[-1])
                self.assertNotIn(marker, json.dumps(result))
                self.assertTrue({'state', 'stocks', 'historical_start', 'entity_registry',
                                 'params_digest', 'state_digest', 'restore_id'}.isdisjoint(keys(result)))
        self.assertEqual(self.bytes_snapshot(), before)

    def test_excess_unsupported_and_stale_fields_reject_without_campaign_effects(self):
        packet = self.source_options()
        rise, quay = [self.draft(profile) for profile in packet['profiles']]
        bad_drafts = []
        for changes in ({'script': 'untrusted'}, {'profile_id': 'unknown'},
                        {'classification': 'historical'}, {'review_digest': 'stale'},
                        {'choices': {**rise['choices'], 'offer_profile': 'unknown'}}):
            bad_drafts.append({**copy.deepcopy(rise), **changes})
        stale = copy.deepcopy(quay)
        stale['choices']['snapshot_sha256'] = '0' * 64
        bad_drafts.extend([stale, {'schema_version': 'unknown'}, None,
                           {**rise, 'draft_id': 'x' * 33000},
                           {**rise, 'choices': {**rise['choices'], 'founder_name': float('nan')}}])
        before = self.bytes_snapshot()
        with patch.object(Store, 'write', side_effect=AssertionError('Invalid preview wrote a campaign')):
            for draft in bad_drafts:
                with self.subTest(draft_type=type(draft).__name__):
                    self.assertEqual(self.call('/api/creator/drafts/preview',
                                               {'draft': draft, 'options_digest': packet['options_digest']})[0], 400)
            for extra in ({'owner': 'forged'}, {'id': self.existing['id']}, {'explicitly_accepted': True}):
                self.assertEqual(self.call('/api/creator/drafts/preview',
                                           {'draft': rise, 'options_digest': packet['options_digest'], **extra})[0], 400)
            from settlement_setup import MODEL
            with patch.dict(MODEL, {'travel_seconds': MODEL['travel_seconds'] + 1}), \
                    patch('world_draft.preview_initialization') as initialize:
                code, error = self.call('/api/creator/drafts/preview',
                                         {'draft': rise, 'options_digest': packet['options_digest']})
                self.assertEqual(code, 400, error)
                self.assertIn('changed', error['error'])
                initialize.assert_not_called()
        self.assertEqual(self.bytes_snapshot(), before)

    def test_preview_identity_cannot_address_a_saved_campaign_or_create_route(self):
        packet = self.source_options()
        draft = self.draft(packet['profiles'][0])
        before = self.bytes_snapshot()
        with patch.object(Store, 'write', side_effect=AssertionError('Preview identity wrote a campaign')):
            code, result = self.call('/api/creator/drafts/preview',
                                     {'draft': draft, 'options_digest': packet['options_digest']})
            self.assertEqual(code, 200, result)
            self.assertEqual(self.call('/api/playthrough/' + draft['draft_id'], creator=False)[0], 404)
            self.assertEqual(self.call('/api/action',
                {'id': draft['draft_id'], 'revision': 0, 'actor': result['actor_view']['actor_id'],
                 'request_id': 'preview-is-not-a-save', 'kind': 'scene_action',
                 'action_id': 'look-quay', 'text': 'I look around.'}, creator=False)[0], 400)
            self.assertEqual(self.call('/api/creator/drafts/create',
                                      {'draft': draft, 'explicitly_accepted': True})[0], 404)
        self.assertEqual(self.bytes_snapshot(), before)


if __name__ == '__main__':
    unittest.main()
