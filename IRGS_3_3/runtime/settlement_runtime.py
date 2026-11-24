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
    ('inspect', 'Inspect your surroundings', 'Read local committed facts. No elapsed time.'),
    # Opt-in reviewed needs profile rise-needs-1. Without it these attempts fail safely.
    ('feed_household', 'Feed your household', 'At your stores; each hungry member present eats one free grain portion, never the protected seed.'),
    ('rest', 'Rest', 'You and idle household members here rest: two hours with a completed shelter, otherwise four.'),
    ('request_relief', 'Ask Elin for relief', 'At the commons after a recorded shortfall; Elin decides, and relief is owed back as footpath upkeep.'),
    ('path_upkeep', 'Work on the footpath', 'At the clearing while relief is owed; up to one hour of upkeep, needing no materials.')]


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
    return sum(p['timber'] if material == 'timber' else p.get('axe', 1) if material == 'axe' else 0
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


def _needs_on(s):
    return isinstance(s.get('needs_rules'), dict)


def _tired(s, actor):
    return (_needs_on(s) and actor in s['needs']
            and s['needs'][actor]['worked_since_rest'] >= s['needs_rules']['fatigue_work_seconds'])


def _can_work(s, worker):
    if not _needs_on(s) or worker not in s['needs']: return
    assert not s['needs'][worker]['hungry'], 'a hungry person cannot start work until fed'
    assert not _tired(s, worker), 'a tired person cannot start work until rested'


def _open_obligation(s, household):
    found = [o for o in s.get('relief_obligations', {}).values()
             if o['debtor'] == household and o['status'] == 'open']
    assert len(found) <= 1
    return found[0] if found else None


def _start(s, household, worker, *, resume=False):
    model = s['settlement_model']
    _can_work(s, worker)
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
    if _needs_on(s) and actor in s['needs']:
        # Only the actor's own household members who are here are described.
        household = household_of(s, actor)
        limit = s['needs_rules']['fatigue_work_seconds']
        for member in s['households'][household]['members']:
            if location(s, member) != site: continue
            need = s['needs'][member]
            state = [w for w, on in (('hungry', need['hungry']), ('tired', need['worked_since_rest'] >= limit)) if on]
            messages.append(f"{s['actors'][member]['name']}: {' and '.join(state) if state else 'fed and rested'} "
                            f"({need['worked_since_rest'] // 60} of {limit // 60} work minutes since rest).")
        obligation = _open_obligation(s, household)
        if obligation:
            left = obligation['owed_seconds'] - obligation['discharged_seconds']
            messages.append(f'You owe Steward Elin {left // 60} minutes of footpath upkeep for relief grain.')
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
    if _needs_on(s):
        # Fatigue is a material boundary: work stops when the limit is reached.
        limit = s['needs_rules']['fatigue_work_seconds']
        candidates.extend(now + limit - s['needs'][p['worker']]['worked_since_rest']
                          for p in s['projects'].values()
                          if p['status'] == 'active' and p['worker'] in s['needs']
                          and s['needs'][p['worker']]['worked_since_rest'] < limit)
    end = min(candidates)
    assert end > now
    delta = end - now
    s['elapsed_time']['seconds'] = end
    advance_travel(s, delta, s['clock'] if causal_at is None else causal_at)
    for key, project in s['projects'].items():
        if project['status'] != 'active': continue
        h = project['household']
        worker = project['worker']
        if project['kind'] == 'upkeep':
            # Footpath upkeep needs only its worker on site; no materials or tools.
            if location(s, worker) != project['site']:
                project['status'] = 'held'; continue
        # Revocation or unavailable inputs holds only this project. Retain work.
        elif (location(s, worker) != project['site']
                or s['stock_accounts'][h]['site'] != project['site']
                or s['stocks'][h].get('timber', 0) < project['timber']
                or s['stocks'][h].get('axe', 0) < 1):
            project['status'] = 'held'; continue
        if _needs_on(s) and worker in s['needs'] and (s['needs'][worker]['hungry'] or _tired(s, worker)):
            project['status'] = 'held'; continue
        if project['kind'] == 'shelter':
            try: _permission(s, h, 'temporary_dwelling')
            except (AssertionError, KeyError):
                project['status'] = 'held'; continue
        project['worked'] += delta
        if _needs_on(s) and worker in s['needs']:
            s['needs'][worker]['worked_since_rest'] += delta
        if project['kind'] == 'upkeep':
            if project['worked'] == project['duration']:
                project['status'] = 'complete'
                obligation = s['relief_obligations'][project['obligation']]
                obligation['discharged_seconds'] += project['duration']
                if obligation['discharged_seconds'] >= obligation['owed_seconds']:
                    obligation['status'] = 'discharged'
                    obligation['discharged_at'] = end
            elif _tired(s, worker):
                project['status'] = 'held'
            continue
        if project['worked'] != project['duration'] and _tired(s, worker):
            project['status'] = 'held'
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
            if _needs_on(s):
                # Delivered portions go to local members in membership order.
                present = [a for a in household['members'] if location(s, a) == s['stock_accounts'][h]['site']]
                fed = set(present[:delivered // model['grain_per_person']])
                for member in household['members']:
                    s['needs'][member]['hungry'] = member not in fed
                    if member not in fed:
                        for project in s['projects'].values():
                            if project['worker'] == member and project['status'] == 'active':
                                project['status'] = 'held'
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
    elif action == 'feed_household':
        assert _needs_on(s), 'the reviewed needs profile is required'
        model = s['settlement_model']
        assert s['stock_accounts'][household]['site'] == site, 'your household stores must be here'
        hungry = [a for a in s['households'][household]['members']
                  if location(s, a) == site and s['needs'][a]['hungry']]
        count = min(len(hungry), max(0, _free(s, household, 'grain')) // model['grain_per_person'])
        assert count >= 1, 'a hungry member and free grain are required'
        for member in hungry[:count]:
            _consume(s, household, 'grain', model['grain_per_person'], f'feed:{key}:{member}', 'eating after a shortfall')
            s['needs'][member]['hungry'] = False
        names = ', '.join(s['actors'][a]['name'] for a in hungry[:count])
        unfed = len(hungry) - count
        message = (f'{names} eat from the household stores. The protected seed grain is untouched.'
                   + (f' {unfed} remain hungry; no free grain is left.' if unfed else ''))
    elif action == 'rest':
        assert _needs_on(s), 'the reviewed needs profile is required'
        _worker_free(s, actor)
        resting = []
        for member in s['households'][household]['members']:
            if location(s, member) != site: continue
            try: _worker_free(s, member)
            except AssertionError: continue
            resting.append(member)
        rules = s['needs_rules']
        sheltered = any(a['household'] == household and a['site'] == site and a['kind'] == 'shelter'
                        for a in s['assets'].values())
        remaining = rules['rest_seconds_sheltered' if sheltered else 'rest_seconds_unsheltered']
        total = remaining
        while remaining: remaining -= _advance(s, remaining, causal_at=at)
        for member in resting:
            s['needs'][member]['worked_since_rest'] = 0
        names = ', '.join(s['actors'][a]['name'] for a in resting)
        message = (f'{names} rest for {total // 3600} hours' + (' in your shelter.' if sheltered else ' without shelter.')
                   + ' Fatigue is cleared.' + (' Hunger is not changed by resting.' if any(s['needs'][a]['hungry'] for a in resting) else ''))
    elif action == 'request_relief':
        assert _needs_on(s), 'the reviewed needs profile is required'
        # Elin's relief decision belongs to the actual NPC. Recheck current
        # existence and control rather than assuming the setup persists.
        from player_actions import _present
        assert 'elin' not in core.player_ids(s) and _present(s, 'elin')
        assert site == 'commons' and location(s, 'elin') == site
        steward = s['organizations']['steward']
        assert steward['active'] and steward.get('store') == 'steward-store'
        rules = s['needs_rules']
        assessments = [a for k, a in s['provision']['assessments'].items() if a['household'] == household]
        latest = max(assessments, key=lambda a: a['at']) if assessments else None
        latest_key = f"{latest['at']}:{household}" if latest else None
        relieved = {o['shortfall'] for o in s['relief_obligations'].values() if o['debtor'] == household}
        store = s['stocks']['steward-store'].get('grain', 0)
        # Steward Elin's authored decision, made from her own records and store.
        if latest is None or latest['deficit'] <= 0:
            message = 'Elin declines. The commons store gives relief only after a recorded provision shortfall.'
        elif latest_key in relieved:
            message = 'Elin declines. She has already given relief for this shortfall.'
        elif _open_obligation(s, household):
            message = 'Elin declines. She will give no further relief until the footpath upkeep you owe is finished.'
        elif store <= 0:
            message = 'Elin declines. The commons relief store is empty.'
        else:
            members = len(s['households'][household]['members'])
            grain = min(rules['relief_grain_per_member'] * members, store)
            s['stocks']['steward-store']['grain'] -= grain
            s['stocks'][household]['grain'] = s['stocks'][household].get('grain', 0) + grain
            s['relief_transfers'][key] = {'material': 'grain', 'quantity': grain, 'from': 'steward-store',
                'to': household, 'elapsed_seconds': s['elapsed_time']['seconds'], 'source_ref': rules['source_ref']}
            owed = -(-grain // 2) * rules['upkeep_seconds_per_two_grain']
            s['relief_obligations'][key] = {'debtor': household, 'creditor': 'steward', 'kind': 'footpath_upkeep',
                'grain': grain, 'owed_seconds': owed, 'discharged_seconds': 0, 'status': 'open',
                'shortfall': latest_key, 'created_at': s['elapsed_time']['seconds'], 'source_ref': rules['source_ref']}
            message = (f'Elin lends {grain} grain portions from the commons store, and you carry them to your household stores. '
                       f'You owe {owed // 3600} hour(s) of footpath upkeep at the clearing. She will give no further relief until it is done.')
    elif action == 'path_upkeep':
        assert _needs_on(s), 'the reviewed needs profile is required'
        assert site == 'clearing', 'the footpath upkeep is at the clearing'
        obligation_key = next((k for k, o in s['relief_obligations'].items()
                               if o['debtor'] == household and o['status'] == 'open'), None)
        assert obligation_key is not None, 'no footpath upkeep is owed'
        obligation = s['relief_obligations'][obligation_key]
        _can_work(s, actor)
        unfinished = [k for k, p in s['projects'].items() if p['kind'] == 'upkeep'
                      and p['obligation'] == obligation_key and p['status'] in ('held', 'paused')]
        if unfinished:
            project_key = unfinished[0]
            assert s['projects'][project_key]['worker'] == actor
            _worker_free(s, actor, project_key)
            s['projects'][project_key]['status'] = 'active'
        else:
            _worker_free(s, actor)
            scheduled = sum(p['duration'] for p in s['projects'].values()
                            if p['kind'] == 'upkeep' and p['obligation'] == obligation_key)
            remaining = obligation['owed_seconds'] - scheduled
            assert remaining > 0, 'all owed upkeep is already scheduled'
            project_key = 'upkeep:' + key
            s['projects'][project_key] = {'household': household, 'worker': actor, 'site': 'clearing',
                'kind': 'upkeep', 'duration': min(s['needs_rules']['upkeep_project_seconds'], remaining),
                'worked': 0, 'timber': 0, 'axe': 0, 'status': 'active', 'obligation': obligation_key,
                'source_ref': s['needs_rules']['source_ref'], 'authority': 'explicit-player-request'}
        message = 'You begin footpath upkeep at the clearing. The owed work is not finished until the time is worked.'
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
    assert set(s['stocks']) == set(s['stock_accounts']) and set(s['households']) <= set(s['stocks'])
    for account in set(s['stocks']) - set(s['households']):
        # Only a reviewed institution store may hold stock outside a household.
        assert _needs_on(s) and account == 'steward-store'
        assert s['stock_accounts'][account]['institution'] in s['organizations']
    if _needs_on(s):
        rules = s['needs_rules']
        all_people = {a for h in s['households'].values() for a in h['members']}
        assert set(s['needs']) == all_people
        for need in s['needs'].values():
            assert type(need['hungry']) is bool and type(need['worked_since_rest']) is int
            assert 0 <= need['worked_since_rest'] <= rules['fatigue_work_seconds']
        for o in s['relief_obligations'].values():
            assert o['debtor'] in s['households'] and o['status'] in ('open', 'discharged')
            assert 0 <= o['discharged_seconds'] and o['owed_seconds'] > 0
            assert (o['status'] == 'discharged') == (o['discharged_seconds'] >= o['owed_seconds'])
        assert all(sum(o['status'] == 'open' for o in s['relief_obligations'].values() if o['debtor'] == h) <= 1
                   for h in s['households'])
        for p in s['projects'].values():
            if p['status'] == 'active' and p['worker'] in s['needs']:
                assert not s['needs'][p['worker']]['hungry'] and not _tired(s, p['worker']), 'needs hold work'
            if p['kind'] == 'upkeep':
                assert p['obligation'] in s['relief_obligations'] and p['timber'] == 0 and p['axe'] == 0
    else:
        assert not any(p['kind'] == 'upkeep' for p in s['projects'].values())
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
        assert s['projects'][a['project']]['kind'] != 'upkeep'
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
