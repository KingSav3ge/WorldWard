"""Bounded authored local actions over the selected Core's shared world.

The selected opening supplies explicit fictional geography, custody, consent
and durations. These are not historical measurements or universal rules. Only
this designated actor's received map exposes choices; real conditions and
stock are consulted during execution, never to produce a winning menu.
"""
from __future__ import annotations

import copy

from irgs_reference import InvalidEvent, digest
from player_actions import _controlled, _failed_dependencies, _present


OPERATION = 'execute_player_scene_action'
UNAVAILABLE = 'This action cannot currently be resolved. No action effects or elapsed work were committed.'


class SceneActionUnavailable(InvalidEvent):
    """Safe reason with private observed rejection dependencies."""
    def __init__(self, dependencies):
        super().__init__(UNAVAILABLE)
        self.dependencies = dependencies


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _action(action):
    if (not isinstance(action, dict) or set(action) != {'kind', 'action_id'}
            or action.get('kind') != 'scene_action' or not _text(action.get('action_id'))):
        raise InvalidEvent('Choose a supported local action')


def _rules(state, actor):
    assert _controlled(state, actor), 'actual current player control required'
    rules = state['scene_rules']
    assert type(rules['schema_version']) is int and rules['schema_version'] == 1 and _text(rules['id']), 'selected authored scene required'
    assert rules['actor_id'] == actor and _text(rules['source_ref']), 'scoped scene selection required'
    assert _text(rules['setup_instruction_ref']), 'explicit reviewed setup consent required'
    assert type(rules['received_at']) is int and 0 <= rules['received_at'] <= state['clock'], 'received map required'
    evidence_id = rules['receipt_evidence_id']
    evidence = state['evidence'][evidence_id]
    receipt = state['knowledge'][actor][evidence_id]
    assert evidence['subject'] == actor and evidence['status'] == 'established', 'actual map record required'
    assert _text(evidence['source_ref']) and _text(receipt['source_ref']), 'map provenance required'
    assert (type(receipt['received_at']) is int
            and evidence['recorded_at'] <= receipt['received_at'] <= state['clock']
            and receipt['received_at'] == rules['received_at']), 'map receipt is not current'
    assert _text(rules['elapsed_axis']), 'selected elapsed axis required'
    return rules


def _location(state, actor):
    current = state['actors'][actor]['current']['location']
    assert isinstance(current, dict) and _text(current['value']), 'established current location required'
    evidence = state['evidence'][current['evidence_id']]
    receipt = state['knowledge'][actor][current['evidence_id']]
    assert evidence['subject'] == actor and evidence['status'] == 'established', 'established location evidence required'
    assert (type(current['at']) is int and evidence['recorded_at'] <= current['at'] <= state['clock']
            and type(receipt['received_at']) is int
            and evidence['recorded_at'] <= receipt['received_at'] <= state['clock']), 'current location is not effective or received'
    return current['value']


def scene_options(state, actor_id):
    """Project only received local options, without reading blockers or stock."""
    if not isinstance(state.get('scene_rules'), dict):
        return []
    try:
        rules = _rules(state, actor_id)
        location = _location(state, actor_id)
        place = rules['places'][location]
        options = []
        for action_id in place['actions']:
            action = rules['actions'][action_id]
            if (action['kind'] not in {'move', 'observe', 'deliver', 'contact_decision'} or action['from'] != location
                    or not all(_text(action[field]) for field in ('label', 'description', 'text'))):
                continue
            options.append({'kind': 'scene_action', 'action_id': action_id,
                'title': action['label'], 'description': action['description'], 'text': action['text']})
        return options
    except (AssertionError, KeyError, TypeError, ValueError, InvalidEvent):
        return []


def operate_scene_action(core, state, at, params, *, committed_duration=None):
    """Executed inside Core's cloned transaction and observed ordinary handler."""
    assert set(params) == {'campaign_id', 'source_ref', 'instruction_ref', 'actor', 'action', 'action_event_id'}
    _action(params['action'])
    actor = params['actor']
    rules = _rules(state, actor)
    from process_runtime import reserved_actors
    assert actor not in reserved_actors(state), 'unfinished process reserves this actor'
    # Legacy activity spans use a different coordinate. Until their calendars
    # are explicitly bound, local walking must not bypass an existing actor
    # commitment by treating its causal coordinates as elapsed seconds.
    assert not any(actor in activity['actors'] for activity in state.get('activities', {}).values()), 'existing activity requires an explicit elapsed binding'
    assert _text(params['instruction_ref']) and _text(params['action_event_id']), 'explicit action identity required'
    event_id = params['action_event_id']
    assert event_id not in state.get('scene_action_results', {}), 'scene result already exists'
    location = _location(state, actor)
    place = rules['places'][location]
    action_id = params['action']['action_id']
    assert action_id in place['actions'], 'action is not in the received local map'
    action = rules['actions'][action_id]
    kind = action['kind']
    assert kind in {'move', 'observe', 'deliver', 'contact_decision'} and action['from'] == location, 'local action required'
    assert all(_text(action[field]) for field in ('label', 'text', 'description', 'success_text', 'failure_text'))
    duration = action['duration_seconds']
    assert type(duration) is int and duration > 0, 'explicit positive authored duration required'
    elapsed = state['elapsed_time']
    assert elapsed['axis'] == rules['elapsed_axis'] and _text(elapsed['source_ref']), 'selected elapsed record required'
    assert type(elapsed['seconds']) is int and elapsed['seconds'] >= 0, 'nonnegative elapsed total required'
    status = 'completed_successfully'
    observations = []
    reference = params['source_ref']
    evidence_id = 'scene:' + event_id

    def receive(assertion, key=evidence_id):
        core._operate(state, at, 'record_evidence', {
            'evidence_id': key, 'subject': actor, 'assertion': assertion,
            'status': 'established', 'source_ref': reference, 'originator': actor})
        core._operate(state, at, 'receive_evidence', {
            'evidence_id': key, 'recipient': actor, 'source_ref': reference})

    summary = action['success_text']
    if kind == 'move':
        destination = action['to']
        assert destination in rules['places'], 'actual selected destination required'
        condition_id = action.get('blocked_by')
        blocked = False
        if condition_id is not None:
            condition = state['site_conditions'][condition_id]
            assert type(condition['passable']) is bool and _text(condition['source_ref']), 'supported route condition required'
            blocked = not condition['passable']
        if blocked:
            status = 'completed_unsuccessfully'
            summary = action['failure_text']
            observations.append(summary)
            receive(summary)
        else:
            receive(summary)
            core._operate(state, at, 'confirm_character_field', {
                'subject': actor, 'field': 'location', 'value': destination,
                'evidence_id': evidence_id, 'authority_ref': rules['source_ref'],
                'instruction_ref': params['instruction_ref'], 'source_ref': reference})
            description = rules['places'][destination]['description']
            assert _text(description), 'authored immediate destination view required'
            receive(description, evidence_id + ':arrival')
            observations.append(description)
            core._operate(state, at, 'confirm_character_field', {
                'subject': actor, 'field': 'current_activity', 'value': description,
                'evidence_id': evidence_id + ':arrival', 'authority_ref': rules['source_ref'],
                'instruction_ref': params['instruction_ref'], 'source_ref': reference})
    elif kind == 'observe':
        observation = place['observe']
        assert _text(observation), 'authored local observation required'
        observations.append(observation)
        receive(observation)
    elif kind == 'contact_decision':
        # This reviewed fictional profile selects one independent refusal. Do
        # not infer other preferences, consent, possession or authority.
        contact = action['contact_id']
        assert rules['id'] == 'quay-contact-decision-v1'
        assert action['decision_policy'] == 'quay-contact-declines-carry-v1'
        assert contact == 'FICTIONAL-QUAY-CONTACT' and _present(state, contact)
        assert contact not in core.player_ids(state), 'the contact must make their own decision'
        from settlement_runtime import location as current_location
        assert current_location(state, contact) == location, 'actual local contact required'
        request_id = evidence_id + ':request'
        core._operate(state, at, 'record_evidence', {
            'evidence_id': request_id, 'subject': contact,
            'assertion': 'The courier asks the worker to carry the dispatch.',
            'status': 'testimony', 'originator': actor, 'source_ref': reference})
        core._operate(state, at, 'receive_evidence', {
            'evidence_id': request_id, 'recipient': contact, 'source_ref': reference})
        summary = 'The worker declines to take custody of the dispatch.'
        core._operate(state, at, 'record_evidence', {
            'evidence_id': evidence_id, 'subject': actor, 'assertion': 'I will not carry the dispatch.',
            'status': 'testimony', 'originator': contact, 'source_ref': rules['source_ref']})
        core._operate(state, at, 'receive_evidence', {
            'evidence_id': evidence_id, 'recipient': actor, 'source_ref': rules['source_ref']})
    else:
        material, destination = action['material'], action['destination']
        assert _text(material) and _text(destination) and destination != actor
        assert type(action['quantity']) is int and action['quantity'] == 1, 'selected single dispatch delivery required'
        # The reviewed scene action designates precisely this carried item and
        # recipient. An arbitrary stock location name never grants custody.
        assert destination in state['stocks'], 'actual receiving tray required'
        quantity = state['stocks'][actor][material]
        assert type(quantity) is int and quantity >= 0, 'actual carried dispatch count required'
        deadline = action.get('deadline_seconds')
        if deadline is not None:
            assert type(deadline) is int and deadline > 0 and _text(action['expired_text'])
        if deadline is not None and quantity >= 1 and elapsed['seconds'] + duration > deadline:
            # Selected authored deadline: the attempt takes its time and fails.
            status = 'completed_unsuccessfully'
            summary = action['expired_text']
            observations.append(summary)
        elif quantity < 1:
            status = 'completed_unsuccessfully'
            summary = action['failure_text']
            observations.append(summary)
        else:
            core._operate(state, at, 'transfer_stock', {
                'from': actor, 'to': destination, 'material': material, 'quantity': 1,
                'authority_ref': rules['source_ref'], 'source_ref': reference})
        receive(summary)
    if committed_duration is None:
        elapsed['seconds'] += duration
    else:
        assert kind == 'observe' and committed_duration == duration
    outcome = {'summary': summary, 'kind': kind, 'elapsed_seconds': duration,
               'elapsed_total': elapsed['seconds'], 'observations': observations}
    receipt = {'event_id': event_id, 'at': at, 'operation': OPERATION,
               'actor': actor, 'action_id': action_id}
    state.setdefault('scene_action_results', {})[event_id] = {
        'actor': actor, 'status': status, 'outcome': outcome, 'receipt': receipt}


def execute_scene_action(world, event_id, actor_id, action, instruction_ref):
    """Observe and commit one fresh action; the host durably retrieves retries."""
    from core_world import CoreWorld
    from r9_runtime import observe
    _action(action)
    if not isinstance(world, CoreWorld) or not all(_text(value) for value in (event_id, actor_id, instruction_ref)):
        raise InvalidEvent('Selected Core, action identity, character and explicit instruction required')
    if event_id in world.s['processed']:
        raise InvalidEvent('Retrieve the original request result instead of repeating this event')
    event = {'id': event_id, 'at': world.s['clock'] + 1, 'op': OPERATION,
        'params': {'campaign_id': world.s['campaign_id'], 'source_ref': instruction_ref,
            'instruction_ref': instruction_ref, 'actor': actor_id, 'action': copy.deepcopy(action),
            'action_event_id': event_id}}
    try:
        certificate = observe(world.s, event)
        candidate = CoreWorld(state=world.s)
        candidate.apply(event['id'], event['at'], event['op'], **event['params'])
        assert digest(candidate.s) == certificate['post_state'], 'observed action state changed'
    except (InvalidEvent, AssertionError, KeyError, TypeError, ValueError) as error:
        raise SceneActionUnavailable(_failed_dependencies(world.s, event)) from error
    result = copy.deepcopy(candidate.s['scene_action_results'][event_id])
    result.pop('actor')
    result['dependencies'] = certificate
    world.s = candidate.s
    from offline_responses import render_receipt
    result['presentation'] = render_receipt(world, actor_id, event_id)
    return result
