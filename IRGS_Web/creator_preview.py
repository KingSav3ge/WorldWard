"""Creator-only presentation adapter for two pinned Engine preview profiles.

The HTTP host supplies its existing local-owner Creator guard. These descriptors
mirror existing Engine/ordinary-start controls, not new rules or launch authority.
Every submitted document is revalidated and projected by world_draft; no Store,
receipt index, provider or durable draft/campaign publication belongs here.
"""
import copy
import json

MAX_DRAFT_BYTES = 32000


def _text(identity, title, max_length=80):
    return {'id': identity, 'label': title, 'kind': 'text', 'max_length': max_length}


def _select(identity, title, pairs, *, optional=False):
    return {'id': identity, 'label': title, 'kind': 'select', 'optional': optional,
            'options': [{'id': key, 'label': label} for key, label in pairs]}


def options():
    from irgs_reference import digest
    import world_draft
    from settlement_setup import templates, OFFER_PROFILE
    source = templates()
    rise = next(row for row in source['templates'] if row['id'] == 'R00')
    profiles = [{
        'id': 'rise-r00', 'title': rise['title'], 'classification': 'fictional',
        'available': rise['ready'] is True, 'source_status': rise['status'],
        'source_label': source['model']['source_ref'],
        'rules': copy.deepcopy(source['model']),
        'fields': [
            _text('founder_name', 'Founder name'), _text('household_name', 'Household name'),
            _text('settlement_name', 'Settlement name'), _text('region_name', 'Fictional region'),
            _text('date_label', 'Fictional opening date label'),
            _select('company', 'Starting company', [
                ('solo', 'Solo founder'), ('sibling', 'Founder and adult sibling Rowan'),
                ('two_households', 'Founder and an independent Mira household')]),
            _select('permission', 'Founding permission', [
                ('seek', 'Seek a grant during play'),
                ('held', 'Arrive with a received and accepted limited fictional grant')]),
            _select('supplies', 'Selected founder-household supplies', [
                ('basic', 'Basic supplies'), ('stocked', 'Stocked supplies')]),
            _select('offer_profile', 'Optional household offers', [
                (OFFER_PROFILE, 'Reviewed founder-household offer attempts')], optional=True)]}]
    # world_draft supports exactly this historical setting and the two bounded
    # fictional openings. Never turn all historical entries into draft profiles.
    quay = {'id': 'historical-quay', 'title': 'A fictional life on the historical quay',
            'classification': 'mixed', 'available': False, 'fields': [],
            'source_status': 'Selected dated source unavailable'}
    try:
        from historical_campaigns import historical_entry
        from starting_selection import starting_options
        entry = historical_entry('hyw-1415')
        selected = starting_options(profile_id='military', scenario_id='hundred-years-war',
                                    entry_id='hyw-1415', snapshot_sha256=entry['snapshot_sha256'])
        openings = [row for row in selected['playable_openings']
                    if row['id'] in ('quay-contact-v1', 'quay-contact-decision-v1')]
        quay.update(available=bool(openings), snapshot_sha256=entry['snapshot_sha256'],
                    source_label=selected['as_of']['label'],
                    source_status='Selected dated snapshot; fictional new human and opening',
                    fields=[_text('character_name', 'New fictional character name', 100),
                            _select('opening_id', 'Fictional opening',
                                    [(row['id'], row['title']) for row in openings])],
                    openings=copy.deepcopy(openings))
    except (OSError, ValueError, KeyError):
        # Missing historical source does not promote another entry or block Rise.
        pass
    profiles.append(quay)
    result = {'schema_version': 'irgs-creator-preview-options-1',
              'draft_schema': world_draft.SCHEMA_VERSION, 'profiles': profiles}
    result['options_digest'] = digest(result)
    return result


def preview(draft, options_digest):
    if not isinstance(draft, dict):
        raise ValueError('Submit one supported world draft')
    try:
        encoded = json.dumps(draft, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError):
        raise ValueError('Draft fields must contain finite JSON data') from None
    if len(encoded) > MAX_DRAFT_BYTES:
        raise ValueError('Draft exceeds the 32000-byte preview limit')
    current = options()
    if not isinstance(options_digest, str) or options_digest != current['options_digest']:
        raise ValueError('Selected source or rules changed. Refresh profile choices; your draft is retained.')
    profile = next((row for row in current['profiles']
                    if row['id'] == draft.get('profile_id') and row['available']), None)
    if profile is None:
        raise ValueError('Select an available supported preview profile')
    from world_draft import preview_initialization
    # Exact Engine DTO, including its actual disposable controlled-actor view.
    # App Creator inspection and current campaign actors are never consulted.
    return preview_initialization(copy.deepcopy(draft))
