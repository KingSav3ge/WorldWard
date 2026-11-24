"""Explicit opt-in new-character fiction or reviewed existing-person context.

The historical template is unchanged. This initializer is never a continuing
world migration. Existing-person context has its own sourced pack and consent.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from irgs_reference import digest


PACK = Path(__file__).resolve().parents[1] / 'data' / 'solo_quay_opening.json'
DEADLINE_OPENING = 'quay-deadline-v1'
DEADLINE_SECONDS = 180


def _pack():
    return json.loads(PACK.read_text(encoding='utf-8'))


def _selected_pack(state, opening_id=None):
    entry = state.get('historical_start', {}).get('entry_id') or state.get('binding', {}).get('entry_id')
    if entry == 'hyw-1415':
        pack = _pack()
        if opening_id in ('quay-contact-v1', 'quay-contact-decision-v1'):
            pack['id'] = opening_id
            pack['title'] = 'A dispatch and a quay contact'
            pack['description'] += ' This variant adds one fictional local contact.'
            pack['review'] += (' A fictional quay worker introduces themself at the quay. '
                'You can address them through a local channel while both remain present; '
                'their response, consent, possessions and authority are not established.')
            pack['scope'] = pack['scope'].replace('dialogue, combat', 'autonomous dialogue, combat')
            pack['scope'] += (' This variant supports explicitly submitted local testimony; '
                'it does not supply an NPC response or negotiation outcome.')
            pack['source_ref'] = 'authored-solo-opening:' + opening_id
            pack['contact'] = {'actor_id': 'FICTIONAL-QUAY-CONTACT',
                'name': 'Quay contact', 'species': 'human', 'channel_id': 'quay-local',
                'introduction': 'I am a worker here on the quay.'}
            if opening_id == 'quay-contact-decision-v1':
                pack['title'] = 'A dispatch and a worker’s decision'
                pack['review'] = pack['review'].replace(
                    'their response, consent, possessions and authority are not established.',
                    'their possessions and authority are not established.')
                pack['scope'] = pack['scope'].replace('it does not supply an NPC response or negotiation outcome.',
                    'ordinary speech alone supplies no NPC response or negotiation outcome.')
                pack['review'] += (' In this fictional variant you can ask the worker to carry the dispatch. '
                    'The worker is independently unwilling to take custody; the request takes 15 authored seconds. '
                    'You retain your own delivery instructions and custody. No response is inferred from ordinary speech.')
                pack['scope'] += (' A selected explicit carry request has an authored refusal; '
                    'it does not establish a general NPC policy, transfer or payment.')
                pack['map_text'] += (' You may ask the worker to carry your dispatch; '
                    'the worker makes their own decision and is not under your control.')
                pack['places']['quay']['actions'].append('request-dispatch-help')
                pack['actions']['request-dispatch-help'] = {
                    'kind': 'contact_decision', 'from': 'quay',
                    'label': 'Ask the worker to carry the dispatch',
                    'text': 'Ask the worker to carry the dispatch for you.',
                    'description': 'Ask the nearby worker; a request does not grant consent or transfer custody.',
                    'duration_seconds': 15,
                    'success_text': 'The worker declines to take custody of the dispatch.',
                    'failure_text': 'The worker declines to take custody of the dispatch.',
                    'decision_policy': 'quay-contact-declines-carry-v1',
                    'contact_id': 'FICTIONAL-QUAY-CONTACT'}
        elif opening_id == DEADLINE_OPENING:
            # User-adopted authored need (engine/NEEDS_AND_RELIEF_RULES.md).
            pack['id'] = opening_id
            pack['title'] = 'A dispatch against the hour'
            pack['description'] += ' This variant adds an authored delivery deadline.'
            pack['review'] += (f' The clerk accepts the dispatch only if the hand-over completes within '
                f'{DEADLINE_SECONDS} authored seconds of the opening. A later attempt still takes its time, '
                'fails, and leaves the dispatch with you; the delivery then stays closed.')
            pack['scope'] += (f' Selected delivery deadline: {DEADLINE_SECONDS} seconds. Missing it closes the '
                'delivery; no payment, punishment, office or historical consequence is inferred.')
            pack['map_text'] += (f' The clerk accepts the dispatch only within {DEADLINE_SECONDS} seconds '
                'of your start.')
            pack['source_ref'] = 'authored-solo-opening:' + opening_id
            deliver = pack['actions']['deliver-dispatch']
            deliver['deadline_seconds'] = DEADLINE_SECONDS
            deliver['description'] += f' The clerk accepts it only within {DEADLINE_SECONDS} seconds of your start.'
            deliver['expired_text'] = ('The clerk no longer accepts dispatches; the time allowed has passed. '
                'You still carry the sealed dispatch. No dispatch was handed over.')
        return pack
    from historical_campaigns import SNAPSHOTS
    if (entry not in SNAPSHOTS or state.get('binding', {}).get('scenario_id') != 'hundred-years-war'
            or state.get('historical_start', {}).get('snapshot', {}).get('id') != entry):
        return None
    pack = json.loads((PACK.parent/'coc_local_delivery.json').read_text(encoding='utf-8'))
    original_id = pack['id']
    selected_id = 'coc-' + entry.removeprefix('hyw-') + '-delivery-v1'
    pack = json.loads(json.dumps(pack).replace(original_id, selected_id))
    label = state['historical_start']['opening']['label']
    pack['description'] += ' Selected checkpoint: ' + label + '.'
    return pack


def opening_options(state):
    pack = _selected_pack(state)
    if pack is None:
        return []
    packs = [pack]
    if (state.get('historical_start', {}).get('entry_id') or state.get('binding', {}).get('entry_id')) == 'hyw-1415':
        packs.append(_selected_pack(state, 'quay-contact-v1'))
        packs.append(_selected_pack(state, 'quay-contact-decision-v1'))
        packs.append(_selected_pack(state, DEADLINE_OPENING))
    return [{**{key: copy.deepcopy(pack[key]) for key in
                ('id', 'title', 'description', 'requirements', 'review', 'scope')},
             'content_sha256': digest(pack), 'fictional': True,
             'elapsed_origin_seconds': 0,
             'durations': {'observation_seconds': 20, 'walking_seconds': 45,
                           'shortcut_attempt_seconds': 30, 'delivery_seconds': 10,
                           **({'contact_request_seconds': 15} if pack['id'] == 'quay-contact-decision-v1' else {})}} for pack in packs]


def initialize_opening(world, character, actor_id, reference, *, options=None):
    opening_id = character.get('opening_id')
    if opening_id in (None, ''):
        return world
    historical_person = character.get('kind') == 'existing'
    if historical_person:
        from start_readiness import existing_pack
        pack = existing_pack(world.s, actor_id, opening_id)
        reviewed = next((r for r in (options or {}).get('existing_character_openings', [])
                         if r['id'] == opening_id and r['actor_id'] == actor_id), None)
        if reviewed is None or digest(pack) != reviewed['content_sha256']:
            raise ValueError('The existing-person opening changed after review')
    else:
        pack = _selected_pack(world.s, opening_id)
    species = world.s.get('actors', {}).get(actor_id, {}).get('species')
    if ((not historical_person and character.get('kind') != 'new') or not isinstance(species, str)
            or species.strip().casefold() != 'human'
            or world.s.get('starting_control', {}).get('scenario_id') != 'individual'
            or (not historical_person and opening_id not in {row['id'] for row in opening_options(world.s)})):
        raise ValueError('This authored opening requires a new human character in the selected historical individual Solo start')
    if world.s.get('scene_rules') or world.s.get('elapsed_time'):
        raise ValueError('An opening is initialized only once in a new world')
    if (world.s.get('gameplay_started', {}).get('actor_id') != actor_id
            or any(not event['id'].startswith('setup:') for event in world.s['journal'])):
        raise ValueError('Authored circumstances cannot be inserted into a continuing playthrough')
    from core_world import CoreWorld
    result = CoreWorld(state=world.s)
    source = pack['source_ref']

    def apply(key, op, **params):
        result.apply('setup:scene:' + key, result.s['clock'] + 1, op,
                     campaign_id=result.s['campaign_id'], source_ref=source, **params)

    def evidence(key, assertion):
        apply(key, 'record_evidence', evidence_id='setup:scene-' + key,
              subject=actor_id, assertion=assertion, status='established')
        apply(key + '-receipt', 'receive_evidence', evidence_id='setup:scene-' + key, recipient=actor_id)

    evidence('map', pack['map_text'])
    received_at = result.s['knowledge'][actor_id]['setup:scene-map']['received_at']
    place = pack['initial_place']
    evidence('location', ('Sourced broad opening placement: ' if historical_person else 'Authored opening placement: ')
             + pack['places'][place]['title'] + '.')
    apply('location-confirmed', 'confirm_character_field', subject=actor_id, field='location',
          value=place, evidence_id='setup:scene-location', authority_ref=reference, instruction_ref=reference)
    if not historical_person:
        evidence('activity', pack['places'][place]['description'])
        apply('activity-confirmed', 'confirm_character_field', subject=actor_id, field='current_activity',
              value=pack['places'][place]['description'], evidence_id='setup:scene-activity',
              authority_ref=reference, instruction_ref=reference)
        evidence('dispatch', 'You have custody of one sealed dispatch entrusted for the receiving clerk\'s tray. It supplies no ownership, pay or office.')
        apply('dispatch-stock', 'establish_stock', location=actor_id, material=pack['initial_material'],
              quantity=1, inventory_evidence_ref='setup:scene-dispatch')
        apply('receiving-tray', 'establish_stock', location=pack['destination'], material=pack['initial_material'],
              quantity=0, inventory_evidence_ref='setup:scene-map')
    contact = pack.get('contact')
    if contact:
        other = contact['actor_id']
        apply('contact-actor', 'register_actor', actor_id=other, name=contact['name'],
              species=contact['species'], player_controlled=False)
        apply('contact-location', 'record_evidence', evidence_id='setup:contact-location',
              subject=other, assertion='The fictional contact begins at the quay.', status='established')
        apply('contact-position', 'confirm_character_field', subject=other, field='location',
              value=place, evidence_id='setup:contact-location', authority_ref=source)
        apply('contact-introduction', 'record_evidence', evidence_id='setup:contact-introduction',
              subject=actor_id, originator=other, assertion=contact['introduction'], status='testimony')
        apply('contact-received', 'receive_evidence', evidence_id='setup:contact-introduction', recipient=actor_id)
        result.s['communication_rules'] = {'schema_version': 1, 'source_ref': source,
            'time_model': 'causal_only_no_elapsed_rule', 'channels': {
                contact['channel_id']: {'mode': 'co_located', 'actors': [actor_id, other]}}}
    # Initial authored physical condition and selected local rules belong to
    # this first world initialization, before its first atomic save. They are
    # never reinstalled when loading, inspecting or advancing an existing game.
    result.s['site_conditions'] = copy.deepcopy(pack['conditions'])
    result.s['scene_rules'] = {key: copy.deepcopy(pack[key]) for key in
                              ('schema_version', 'id', 'source_ref', 'elapsed_axis', 'places', 'actions')}
    result.s['scene_rules'].update(actor_id=actor_id, received_at=received_at,
        receipt_evidence_id='setup:scene-map', setup_instruction_ref=reference,
        content_sha256=digest(pack))
    if historical_person:
        result.s['scene_rules']['context_kind'] = pack['classification']
    result.s['elapsed_time'] = {'axis': pack['elapsed_axis'], 'seconds': 0, 'source_ref': source}
    # The setup explicitly gives this character ongoing inspection of the
    # object in their custody; a place name alone grants no inventory access.
    if not historical_person:
        result.s.setdefault('gameplay_visibility', {}).setdefault(actor_id, {}).setdefault('inventory', []).append({
            'active': True, 'source_ref': source, 'received_at': result.s['clock'],
            'access': 'inspect_current', 'location': actor_id, 'material': pack['initial_material']})
    result.s['gameplay_started']['existing_character_opening' if historical_person else 'authored_opening'] = {
        'id': opening_id, 'fictional': not historical_person, 'instruction_ref': reference,
        'content_sha256': digest(pack), 'civil_calendar_advance': False}
    return CoreWorld(state=result.s)
