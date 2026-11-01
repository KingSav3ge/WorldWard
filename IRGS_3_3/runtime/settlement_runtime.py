"""Shared, bounded settlement contracts executed inside CoreWorld.apply.

Owner records stay in the one Core state. Model values are selected in setup;
causal sequence is never used as elapsed time. No autonomous PC decisions.
"""
from irgs_reference import InvalidEvent

OPERATION = 'execute_settlement_action'
SAFE_FAILURE = 'This settlement action could not complete. No effects or elapsed work were saved. Inspect your local records and review its requirements.'
ACTIONS = [
    ('request_grant', 'Ask Elin about founding permission', 'At the commons; receive an offer, without accepting it.'),
    ('accept_grant', 'Accept the limited grant', 'At the commons; camp and temporary dwelling only, preserving the seasonal path.'),
    ('walk_clearing', 'Walk to the clearing', 'Five minutes under the selected fictional travel model.'),
    ('walk_commons', 'Walk to the commons', 'Five minutes; active workers remain at their job.'),
    ('found', 'Establish your named camp', 'At the clearing with accepted permission. Creates no building or supplies.'),
    ('build', 'Start building shelter yourself', 'At your camp; reserve three timber bundles and one axe for one hour of work.'),
    ('delegate', 'Ask Rowan to build the shelter', 'Requires the reviewed sibling company, Rowan present and willing, with the same finite inputs.'),
    ('pause', 'Pause the shelter project', 'Retains completed work and releases the worker and unconsumed inputs.'),
    ('resume', 'Resume the shelter project', 'At the camp with its worker, permission, tools and remaining inputs available.'),
    ('invite', 'Discuss moving with Oren', 'At the commons; communicate your established camp and receive Oren’s response.'),
    ('arrange_departure', 'Arrange Oren’s departure', 'At the commons after consent; Oren travels with private goods and joins only on arrival.'),
    ('wait_hour', 'Let one hour pass', 'Advance qualified work, travel and provision; return at the first completion or provision boundary.'),
    ('inspect', 'Inspect your surroundings', 'Read local committed facts. No elapsed time.')]


def household_of(s, actor):
    matches = [key for key, h in s['households'].items() if actor in h['members']]
    assert len(matches) == 1, 'one household per physical person'
    return matches[0]


def location(s, actor):
    value = s['actors'][actor]['current'].get('location')
    if isinstance(value, dict): value = value.get('value')
    return value if isinstance(value, str) and value.strip() else None


def notice(s, actor, at, key, text):
    records = s['settlement_receipts'].setdefault(actor, {})
    assert key not in records, 'receipt identity already used'
    records[key] = {'text': text, 'recorded_at': at, 'elapsed_seconds': s['elapsed_time']['seconds']}


def _reserved_material(s, household, material, *, excluding=None):
    """Unconsumed inputs reserved by active projects in this household.

    Internal Core accounting only; this does not reserve a building place,
    establish an allowance, transfer stock, or expose another actor's records.
    """
    return sum(p['timber'] if material == 'timber' else 1 if material == 'axe' else 0
               for key, p in s['projects'].items()
               if key != excluding and p['household'] == household and p['status'] == 'active')


def _free(s, household, material, *, excluding=None):
    reserved = _reserved_material(s, household, material, excluding=excluding)
    seed = s['households'][household]['seed_reserve'] if material == 'grain' else 0
    return s['stocks'][household].get(material, 0) - reserved - seed


def _consume(s, household, material, quantity, key, purpose):
    assert key not in s['material_flows'] and type(quantity) is int and quantity > 0
    assert s['stocks'][household][material] >= quantity
    s['stocks'][household][material] -= quantity
    s['material_flows'][key] = {'material': material, 'quantity': quantity, 'kind': 'consumption',
        'account': household, 'purpose': purpose, 'elapsed_seconds': s['elapsed_time']['seconds'],
        'source_ref': s['settlement_model']['source_ref']}


def _permission(s, household, right):
    grant = s['grants'].get('founding')
    assert grant and grant['household'] == household and grant['status'] == 'accepted' and grant['active']
    issuer = s['organizations'][grant['issuer']]
    assert issuer['active'] and issuer['parcel'] == grant['site'] == 'clearing'
    assert right in grant['rights'] and right in issuer['rights'], 'current scoped permission required'


def _worker_free(s, worker, excluding=None):
    from process_runtime import reserved_actors
    assert worker not in reserved_actors(s), 'unfinished process reserves this actor'
    assert not any(p['worker'] == worker and p['status'] == 'active' for key, p in s['projects'].items() if key != excluding)
    assert not any(worker in m['members'] and m['status'] == 'transit' for m in s['migrations'].values())
    # Shared capacity bookings use a different coordinate. Do not guess a mapping.
    assert not any(worker in a['actors'] for a in s.get('activities', {}).values()), 'unmapped capacity booking holds this worker'


def _start(s, household, worker, *, resume=False):
    model = s['settlement_model']
    _permission(s, household, 'temporary_dwelling')
    assert location(s, worker) == 'clearing' and household in s['settlements']['camp']['households']
    assert worker in s['households'][household]['members']
    _worker_free(s, worker, 'shelter' if resume else None)
    assert s['stock_accounts'][household]['site'] == 'clearing'
    assert _free(s, household, 'timber', excluding='shelter') >= model['shelter_timber']
    assert _free(s, household, 'axe', excluding='shelter') >= 1
    if resume:
        project = s['projects']['shelter']
        assert project['status'] == 'paused' and project['worker'] == worker
        project['status'] = 'active'
    else:
        assert 'shelter' not in s['projects'], 'new identity cannot duplicate this physical project'
        s['projects']['shelter'] = {'household': household, 'worker': worker, 'site': 'clearing',
            'kind': 'shelter', 'duration': model['shelter_seconds'], 'worked': 0,
            'timber': model['shelter_timber'], 'status': 'active', 'source_ref': model['source_ref'],
            'authority': 'explicit-player-request' if worker == 'founder' else 'reviewed-bounded-consent'}


def inspect_local(s, actor, at, key):
    site = location(s, actor)
    messages = []
    for project in s['projects'].values():
        if project['site'] == site:
            messages.append(f"{s['actors'][project['worker']]['name']}'s {project['kind']} project is {project['status']} ({project['worked']}/{project['duration']} seconds worked).")
    if site == 'clearing' and 'camp' in s['settlements']:
        members = sum(len(s['households'][h]['members']) for h in s['settlements']['camp']['households'])
        places = sum(a['places'] for a in s['assets'].values() if a['site'] == site)
        messages.append(f'The camp has {members} residents and {places} completed shelter places. Shelter shortage: {max(0, members-places)}.')
    notice(s, actor, at, key, ' '.join(messages) or 'You inspect the local surroundings; no new physical effects occur.')


def _advance(s, seconds, *, causal_at=None):
    from process_runtime import advance_travel, travel_boundaries
    model = s['settlement_model']
    assert type(seconds) is int and 0 < seconds <= model['max_advance_seconds']
    now = s['elapsed_time']['seconds']
    target = now + seconds
    # An elapsed request returns at the earliest material boundary. Movement
    # runs the same scheduler but completes its already selected short route.
    candidates = [target, s['provision']['next_at']]
    candidates.extend(travel_boundaries(s, now))
    candidates.extend(now + p['duration'] - p['worked'] for p in s['projects'].values() if p['status'] == 'active')
    candidates.extend(m['arrive_at'] for m in s['migrations'].values() if m['status'] == 'transit')
    end = min(candidates)
    assert end > now
    delta = end - now
    s['elapsed_time']['seconds'] = end
    advance_travel(s, delta, s['clock'] if causal_at is None else causal_at)
    for key, project in s['projects'].items():
        if project['status'] != 'active': continue
        h = project['household']
        # Revocation or unavailable inputs holds only this project. Retain work.
        if (location(s, project['worker']) != project['site']
                or s['stock_accounts'][h]['site'] != project['site']
                or s['stocks'][h].get('timber', 0) < project['timber']
                or s['stocks'][h].get('axe', 0) < 1):
            project['status'] = 'held'; continue
        if project['kind'] == 'shelter':
            try: _permission(s, h, 'temporary_dwelling')
            except (AssertionError, KeyError):
                project['status'] = 'held'; continue
        project['worked'] += delta
        if project['worked'] == project['duration']:
            _consume(s, h, 'timber', project['timber'], 'project:' + key, 'accepted ' + project['kind'])
            project['status'] = 'complete'
            s['assets'][key] = {'kind': 'shelter', 'household': h, 'site': project['site'],
                'places': model['shelter_places'], 'accepted_at': end, 'project': key}
    # Arrival is physical movement of existing people and goods, not new stock.
    for migration in s['migrations'].values():
        if migration['status'] == 'transit' and migration['arrive_at'] == end:
            h = migration['household']
            for actor in migration['members']: s['actors'][actor]['current']['location'] = migration['to']
            s['stock_accounts'][h]['site'] = migration['to']
            migration['status'] = 'arrived'
            s['households'][h]['settlement'] = 'camp'
            s['settlements']['camp']['households'].append(h)
    if end == s['provision']['next_at']:
        for h, household in s['households'].items():
            demand = len(household['members']) * model['grain_per_person']
            local = sum(location(s, a) == s['stock_accounts'][h]['site'] for a in household['members'])
            delivered = min(max(0, _free(s, h, 'grain')), local * model['grain_per_person'])
            if delivered: _consume(s, h, 'grain', delivered, f'provision:{end}:{h}', 'household provision')
            s['provision']['assessments'][f'{end}:{h}'] = {'household': h, 'at': end, 'demand': demand,
                'delivered': delivered, 'deficit': demand-delivered}
        s['provision']['next_at'] += model['provision_interval_seconds']
    return delta


def operate_settlement_action(core, s, at, p):
    actor, action = p['actor'], p['action']
    assert s['binding']['campaign_profile'] == 'rise' and s['rise']['review_digest']
    assert s['settlement_model']['id'] == s['rise']['version'] and s['settlement_model']['source_ref']
    assert actor in core.player_ids(s) and actor == 'founder', 'explicit current founder control required'
    assert action in {key for key, _, _ in ACTIONS} and p['instruction_ref']
    assert isinstance(p['request_id'], str) and p['request_id']
    household = household_of(s, actor)
    site = location(s, actor)
    key = p['request_id']
    if action == 'request_grant':
        assert site == 'commons' and location(s, 'elin') == site
        issuer = s['organizations']['steward']
        assert issuer['active'] and issuer['parcel'] == 'clearing'
        assert 'founding' not in s['grants']
        s['grants']['founding'] = {'issuer': 'steward', 'household': household, 'site': 'clearing',
            'rights': ['camp', 'temporary_dwelling'], 'status': 'offered', 'active': True,
            'source_ref': p['source_ref'], 'offered_to': actor}
        message = 'Elin offers camp and temporary-dwelling rights at the clearing. Preserve the seasonal footpath. No supplies, forest rights or government authority are included. You have not accepted.'
    elif action == 'accept_grant':
        assert site == 'commons' and location(s, 'elin') == site
        g = s['grants']['founding']
        assert g['status'] == 'offered' and g['offered_to'] == actor and g['active']
        assert s['organizations'][g['issuer']]['active']
        g['status'] = 'accepted'; g['accepted_ref'] = p['instruction_ref']
        message = 'You accept the limited grant and its obligation to preserve the seasonal footpath. No goods change hands.'
    elif action in ('walk_clearing', 'walk_commons'):
        _worker_free(s, actor)
        destination = 'clearing' if action == 'walk_clearing' else 'commons'
        assert site != destination
        companions = s['households'][household]['members'] if 'camp' not in s['settlements'] else [actor]
        for member in companions:
            _worker_free(s, member)
            s['actors'][member]['current']['location'] = 'route:' + site + '-' + destination
        if 'camp' not in s['settlements']:
            s['stock_accounts'][household]['site'] = 'route:' + site + '-' + destination
        # A route is already selected. Process intermediate boundaries before arrival.
        remaining = s['settlement_model']['travel_seconds']
        while remaining: remaining -= _advance(s, remaining, causal_at=at)
        s['actors'][actor]['current']['location'] = destination
        if 'camp' not in s['settlements']:
            for member in s['households'][household]['members']:
                _worker_free(s, member); s['actors'][member]['current']['location'] = destination
            s['stock_accounts'][household]['site'] = destination
        message = 'You arrive at the ' + destination + '.'
    elif action == 'found':
        assert site == 'clearing' and 'camp' not in s['settlements']
        _permission(s, household, 'camp')
        s['settlements']['camp'] = {'name': s['rise']['choices']['settlement_name'], 'site': site,
            'households': [household], 'founded_at': s['elapsed_time']['seconds']}
        s['households'][household]['settlement'] = 'camp'
        message = 'You establish ' + s['settlements']['camp']['name'] + '. The path remains in use; the camp has no completed shelter yet.'
    elif action in ('build', 'delegate', 'resume'):
        assert site == 'clearing'
        worker = 'rowan' if action == 'delegate' else (s['projects']['shelter']['worker'] if action == 'resume' else actor)
        if worker != actor:
            assert worker == 'rowan' and s['rise']['choices']['company'] == 'sibling', 'bounded reviewed consent required'
        _start(s, household, worker, resume=action == 'resume')
        message = s['actors'][worker]['name'] + ' begins the shelter work. Inputs are reserved; the shelter is not complete.'
    elif action == 'pause':
        project = s['projects']['shelter']
        assert site == project['site'], 'local instruction required'
        assert project['household'] == household and project['status'] in ('active', 'held')
        project['status'] = 'paused'
        message = 'The shelter work is paused. Its progress is retained and its inputs are released.'
    elif action == 'invite':
        # This selected decision belongs to the actual NPC, never to a player.
        # Recheck current existence/control instead of assuming the setup persists.
        from player_actions import _present
        assert 'oren' not in core.player_ids(s) and _present(s, 'oren')
        assert site == 'commons' and location(s, 'oren') == site and 'camp' in s['settlements']
        assert 'oren-move' not in s['migrations']
        _permission(s, household, 'camp')
        notice(s, 'oren', at, key + ':invitation', 'The founder describes an established camp at the clearing and invites your household to move there, retaining your goods and control of your labor.')
        # An authored local choice: Oren requires a completed repair and means
        # to move, and retains control of household labor and property.
        ready = (s['projects']['oren-repair']['status'] == 'complete'
                 and s['stocks']['oren-home']['grain'] > s['households']['oren-home']['seed_reserve'])
        if ready:
            s['migrations']['oren-move'] = {'household': 'oren-home', 'members': ['oren'], 'from': site,
                'to': 'clearing', 'status': 'agreed', 'source_ref': p['source_ref'],
                'consent': 'authored-local-choice:finished-repair-and-provisioned'}
            message = 'You describe the camp. Oren agrees to move after finishing the repair, bringing private goods. Oren has not departed and offers no labor delegation.'
        else:
            # The received refusal does not disclose private stock or project state.
            # No migration or continuing obligation is created; a later invitation
            # is a new explicit request and is evaluated against the then-current state.
            message = 'You describe the camp. Oren declines to move at this time. No departure or labor agreement is made.'
    elif action == 'arrange_departure':
        # The founder cannot direct a now-player-controlled or absent person,
        # even when an earlier NPC agreement remains in history.
        from player_actions import _present
        assert 'oren' not in core.player_ids(s) and _present(s, 'oren')
        assert site == 'commons'
        _permission(s, household, 'camp')
        migration = s['migrations']['oren-move']
        assert migration['status'] == 'agreed' and location(s, 'oren') == site
        _worker_free(s, 'oren')
        migration['status'] = 'transit'
        migration['depart_at'] = s['elapsed_time']['seconds']
        migration['arrive_at'] = migration['depart_at'] + s['settlement_model']['migration_seconds']
        s['actors']['oren']['current']['location'] = 'route:commons-clearing'
        s['stock_accounts']['oren-home']['site'] = 'route:commons-clearing'
        message = 'Oren departs with private supplies. Membership and local service demand change only on arrival.'
    elif action == 'wait_hour':
        delta = _advance(s, 3600, causal_at=at)
        message = f'{delta} elapsed seconds pass. You retain control at this process boundary.'
    else:
        message = 'You inspect the local situation.'
    notice(s, actor, at, key, message)
    inspect_local(s, actor, at, key + ':inspection')


def validate_settlement(s):
    if 'settlement_model' not in s: return
    assert s['binding']['campaign_profile'] == 'rise'
    assert s['elapsed_time']['axis'] == 'settlement-seconds'
    assert type(s['elapsed_time']['seconds']) is int and s['elapsed_time']['seconds'] >= 0
    all_members = [a for h in s['households'].values() for a in h['members']]
    assert len(all_members) == len(set(all_members)) and set(all_members) <= set(s['actors'])
    assert set(s['stocks']) == set(s['stock_accounts']) == set(s['households'])
    for h, household in s['households'].items():
        assert type(household['seed_reserve']) is int and household['seed_reserve'] >= 0
        assert s['stock_accounts'][h]['household'] == h
    active = [p for p in s['projects'].values() if p['status'] == 'active']
    assert len({p['worker'] for p in active}) == len(active)
    assert not any(p['worker'] in a['actors'] for p in active for a in s.get('activities', {}).values()), 'unmapped shared capacity booking conflicts with settlement work'
    for p in s['projects'].values():
        assert p['worker'] in s['households'][p['household']]['members']
        assert type(p['worked']) is int and 0 <= p['worked'] <= p['duration']
        assert p['status'] in ('active', 'paused', 'held', 'complete')
        assert (p['worked'] == p['duration']) == (p['status'] == 'complete')
    for h in s['households']:
        assert _free(s, h, 'timber') >= 0 and _free(s, h, 'axe') >= 0, 'finite shared reservations'
    for key, a in s['assets'].items():
        assert s['projects'][a['project']]['status'] == 'complete'
        assert 'project:' + key in s['material_flows']
    for m in s['migrations'].values():
        assert m['members'] == s['households'][m['household']]['members']
        assert m['status'] in ('agreed', 'transit', 'arrived')
    for camp in s['settlements'].values():
        assert len(camp['households']) == len(set(camp['households']))


def execute(world, request_id, actor, action, source_ref):
    """One ordinary observed operation; failures disclose no private validator facts."""
    from r9_runtime import observe
    event = {'id': 'settlement:' + request_id, 'at': world.s['clock'] + 1, 'op': OPERATION,
        'params': {'campaign_id': world.s['campaign_id'], 'source_ref': source_ref,
                   'instruction_ref': source_ref, 'actor': actor, 'action': action, 'request_id': request_id}}
    try:
        certificate = observe(world.s, event)
        world.apply(event['id'], event['at'], event['op'], **event['params'])
    except (InvalidEvent, AssertionError, KeyError, TypeError, ValueError) as err:
        raise InvalidEvent(SAFE_FAILURE) from err
    from offline_responses import render_receipt
    return {'event_id': event['id'], 'certificate': certificate,
            'presentation': render_receipt(world, actor, event['id'])}
