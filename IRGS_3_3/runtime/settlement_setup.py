"""Rise configuration compiler. Definitions and reviewed choices, never a simulator.

R00 is an explicitly fictional model selection, not historical calibration.
The other eight families share this catalogue/preview contract and remain held
until their missing content and providers have been qualified.
"""
import copy
from irgs_reference import digest
from core_world import CoreWorld

VERSION = 'rise-foundation-1'
SOURCE = 'authored-fictional:greywater-reach:v1'
COMMUNICATION_SOURCE = 'authored-fictional:greywater-reach:local-introductions:v1'
INTRODUCTIONS = {'elin': 'I am Steward Elin.', 'oren': 'I am Oren.'}
OFFER_PROFILE = 'founder-household-offer-v1'
OFFER_SOURCE = 'authored-fictional:greywater-reach:founder-household-offer:v1'
NEEDS_PROFILE = 'rise-needs-1'
NEEDS_SOURCE = 'adopted-user-rule:rise-needs-1:2026-11-24'
# User-adopted, uncalibrated fictional rules (engine/NEEDS_AND_RELIEF_RULES.md).
NEEDS_RULES = {
    'id': NEEDS_PROFILE, 'source_ref': NEEDS_SOURCE, 'status': 'adopted fictional rule; uncalibrated',
    'fatigue_work_seconds': 14400, 'rest_seconds_sheltered': 7200, 'rest_seconds_unsheltered': 14400,
    'relief_store_grain': 8, 'relief_grain_per_member': 2,
    'upkeep_seconds_per_two_grain': 3600, 'upkeep_project_seconds': 3600,
    'summary': ('Hunger: a member left unfed at a provision boundary is hungry and cannot work until fed. '
                'Fatigue: after 4 hours of work since resting a person is tired and cannot work; rest takes '
                '2 hours with a completed shelter, otherwise 4 hours. Relief: after a recorded shortfall Steward '
                'Elin may lend 2 grain portions per member from a finite 8-portion store, owed back as 1 hour of '
                'footpath upkeep per 2 portions; she refuses further relief while upkeep is owed.'),
    'limits': ['No injury, illness or death is inferred from hunger or fatigue.',
               'Eating is assigned no elapsed time by this rule.',
               'Relief lends existing steward stock; it creates no grain.']}
FAMILIES = [
    ('H01', 'Eastern Sicily'), ('H02', 'Augusta Emerita district'),
    ('H03', 'Silesian village foundation'), ('H04', 'Musashino reclamation'),
    ('H05', 'Volga settlement'), ('H06', 'Prairie homestead'),
    ('N01', 'New world founding'), ('F01', 'Humans in elven lands')]
MODEL = {
    'id': VERSION, 'source_ref': SOURCE, 'status': 'authored demonstration; uncalibrated',
    'travel_seconds': 300, 'shelter_seconds': 3600, 'shelter_timber': 3,
    'shelter_places': 2, 'repair_seconds': 1800, 'repair_timber': 1,
    'provision_interval_seconds': 21600, 'grain_per_person': 1,
    'protected_seed_grain': 2, 'migration_seconds': 900, 'max_advance_seconds': 21600,
    'units': {'grain': 'portions', 'timber': 'prepared bundles', 'axe': 'serviceable tools'},
    'limits': ['No crop, trade, health, combat, death or succession resolver.',
               'Provision deficits are recorded; no injury or death is inferred.',
               'Elapsed seconds do not infer or advance a civil calendar.',
               'Only the disclosed local permission, work and migration procedures are supported.']}
FIELDS = {'template_id', 'founder_name', 'household_name', 'settlement_name',
          'region_name', 'date_label', 'company', 'permission', 'supplies'}


def templates():
    return {'version': VERSION, 'templates': [
        {'id': 'R00', 'title': 'Greywater Reach', 'ready': True,
         'status': 'Fictional founding demonstration',
         'summary': 'Seek permission, establish a camp, build shelter and invite a neighboring household.'},
        *[{'id': key, 'title': title, 'ready': False,
           'status': 'Design family; executable opening held',
           'missing': ['Qualified opening manifest, local permission and material models']}
          for key, title in FAMILIES]], 'model': copy.deepcopy(MODEL)}


def preview(choices):
    optional = {'offer_profile', 'needs_profile'}
    if not isinstance(choices, dict) or not FIELDS <= set(choices) <= FIELDS | optional:
        raise ValueError('Review every setup field; unsupported choices cannot be inferred')
    choices = copy.deepcopy(choices)
    if 'offer_profile' in choices and choices['offer_profile'] != OFFER_PROFILE:
        raise ValueError('Select a supported optional offer profile')
    if 'needs_profile' in choices and choices['needs_profile'] != NEEDS_PROFILE:
        raise ValueError('Select a supported optional needs profile')
    if choices['template_id'] != 'R00':
        raise ValueError('This start family has no qualified executable opening yet')
    for field in ('founder_name', 'household_name', 'settlement_name', 'region_name', 'date_label'):
        value = choices[field]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
            raise ValueError('Supply each name and fictional date using 1–80 characters')
        if any(ord(char) < 32 for char in value):
            raise ValueError('Names and dates must use printable text')
        choices[field] = value.strip()
    if choices['company'] not in ('solo', 'sibling', 'two_households'):
        raise ValueError('Select a supported starting company')
    if choices['permission'] not in ('seek', 'held') or choices['supplies'] not in ('basic', 'stocked'):
        raise ValueError('Select permission and actual supplies separately')
    company = {'solo': ['Founder only'],
               'sibling': ['Founder', 'Rowan, an adult sibling who consents to bounded shelter work'],
               'two_households': ['Founder', 'Mira, an independent household with private goods and no labor delegation']}[choices['company']]
    stocks = {'grain': 12, 'timber': 6, 'axe': 1} if choices['supplies'] == 'basic' else {'grain': 20, 'timber': 9, 'axe': 1}
    review = {'version': VERSION, 'choices': choices, 'model': copy.deepcopy(MODEL),
        'company': company, 'founder_household_stocks': stocks,
        'permission': ('No grant. A local steward can offer limited permission; acceptance is your choice.'
                       if choices['permission'] == 'seek' else
                       'A received, accepted fictional grant permits a camp and temporary dwelling at the clearing.'),
        'terms': 'Camp and temporary dwelling, including one consenting incoming household. Preserve the existing seasonal footpath. No forest, taxation or government rights. No grant supplies goods.',
        'neighbors': ('Steward Elin and Oren are known at the commons. Oren has private supplies and an independent repair plan. '
            'You receive their fictional introductions: "I am Steward Elin." and "I am Oren." '
            'You may attempt local speech while co-located; no response, consent or transfer is automatic.'),
        'communication_setup': {'version': 'irgs-rise-local-introductions-1',
            'source_ref': COMMUNICATION_SOURCE, 'channel': 'commons-local',
            'initial_testimony': copy.deepcopy(INTRODUCTIONS), 'supported_commands': ['speak'],
            'elapsed_status': 'not_resolved'},
        'control': 'Only the founder is player controlled. No spouse, debt, political action or additional relationship is generated.',
        'continuation': 'No automatic successor or respawn. This demonstration has no death model.',
        'provenance': SOURCE}
    if choices.get('offer_profile') == OFFER_PROFILE:
        review['offer_setup'] = {'version': OFFER_PROFILE, 'source_ref': OFFER_SOURCE,
            'mandate_id': 'founder-household-offer', 'account': 'founder-home',
            'scope': 'Attempt offers from the founder household only; Core checks custody on proposal and free stock on fulfillment.',
            'notice': 'An offer grants no recipient consent, acceptance, transfer, reserved stock or NPC decision.'}
    if choices.get('needs_profile') == NEEDS_PROFILE:
        review['needs_setup'] = copy.deepcopy(NEEDS_RULES)
    review['review_digest'] = digest(review)
    return review


def initialize(choices, review_digest, campaign_id):
    review = preview(choices)
    if review_digest != review['review_digest']:
        raise ValueError('Setup changed. Review and confirm the current starting facts before creating a campaign')
    c = review['choices']
    s = {'profile': 'IRGS-CORE-3.3', 'core_version': '3.3', 'campaign_id': campaign_id,
        'binding': {'core': '3.3', 'genre_id': 'settlement', 'library_ids': ['shared'], 'campaign_profile': 'rise'},
        'player_actor_ids': ['founder'], 'clock': 0,
        'campaign_time': {'day': 0, 'time': None, 'precision': 'fictional label; elapsed axis only'},
        'registry': {'characters': {}, 'withdrawn_duplicate_ids': [], 'deprecated_spellings': {}},
        'actors': {}, 'evidence': {}, 'knowledge': {}, 'orders': {}, 'stocks': {}, 'opening_stock': {},
        'obligations': {}, 'designs': {}, 'player_actions': [], 'capacities': {}, 'activities': {},
        'journal': [], 'processed': {}, 'pending': [],
        'rise': {'version': VERSION, 'choices': copy.deepcopy(c), 'review_digest': review_digest, 'source_ref': SOURCE},
        'settlement_model': copy.deepcopy(MODEL),
        'elapsed_time': {'axis': 'settlement-seconds', 'seconds': 0},
        'households': {}, 'stock_accounts': {}, 'material_flows': {}, 'projects': {}, 'assets': {},
        'settlements': {}, 'migrations': {}, 'settlement_receipts': {},
        'provision': {'next_at': MODEL['provision_interval_seconds'], 'assessments': {}},
        'organizations': {'steward': {'actor': 'elin', 'parcel': 'clearing', 'rights': ['camp', 'temporary_dwelling'],
                                    'active': True, 'source_ref': SOURCE}},
        'land_claims': {'clearing': {'existing_use': 'seasonal footpath', 'issuer': 'steward', 'source_ref': SOURCE}},
        'grants': {}}

    def person(key, name, household=None):
        s['actors'][key] = {'id': key, 'name': name, 'species': 'human', 'current': {'location': 'commons'}}
        s['knowledge'][key] = {}
        if household:
            s['households'].setdefault(household, {'members': [], 'seed_reserve': 2, 'settlement': None})['members'].append(key)

    def account(household, stock):
        s['stocks'][household] = dict(stock)
        s['stock_accounts'][household] = {'household': household, 'site': 'commons', 'source_ref': SOURCE}
        for material, quantity in stock.items():
            s['opening_stock'][material] = s['opening_stock'].get(material, 0) + quantity

    person('founder', c['founder_name'], 'founder-home')
    if c['company'] == 'sibling': person('rowan', 'Rowan', 'founder-home')
    person('elin', 'Steward Elin')
    person('oren', 'Oren', 'oren-home')
    # Reviewed fictional initial receipts, analogous to the initial settlement
    # notice. They identify speakers, not present authority, consent or stock.
    for speaker, text in INTRODUCTIONS.items():
        key = 'setup:local-introduction:' + speaker
        s['evidence'][key] = {'subject': 'founder', 'assertion': text, 'status': 'testimony',
            'source_ref': COMMUNICATION_SOURCE, 'recorded_at': 0, 'originator': speaker,
            'occurrence_time': None, 'visibility': 'only explicitly received knowledge'}
        s['knowledge']['founder'][key] = {'received_at': 0, 'source_ref': COMMUNICATION_SOURCE}
    s['communication_rules'] = {'schema_version': 1, 'source_ref': COMMUNICATION_SOURCE,
        'time_model': 'causal_only_no_elapsed_rule', 'channels': {
            'commons-local': {'mode': 'co_located', 'actors': ['founder', 'elin', 'oren']}}}
    account('founder-home', review['founder_household_stocks'])
    account('oren-home', {'grain': 4, 'timber': 3, 'axe': 1})
    if c['company'] == 'two_households':
        person('mira', 'Mira', 'mira-home')
        account('mira-home', {'grain': 8, 'timber': 3, 'axe': 1})
    if c.get('needs_profile') == NEEDS_PROFILE:
        # Opt-in reviewed rules. The relief store is an existing conserved
        # institution account at the commons, not new stock.
        s['needs_rules'] = copy.deepcopy(NEEDS_RULES)
        s['needs'] = {a: {'hungry': False, 'worked_since_rest': 0}
                      for h in s['households'].values() for a in h['members']}
        s['stocks']['steward-store'] = {'grain': NEEDS_RULES['relief_store_grain']}
        s['stock_accounts']['steward-store'] = {'institution': 'steward', 'site': 'commons', 'source_ref': NEEDS_SOURCE}
        s['opening_stock']['grain'] += NEEDS_RULES['relief_store_grain']
        s['organizations']['steward']['store'] = 'steward-store'
        s['relief_obligations'] = {}
        s['relief_transfers'] = {}
    s['households']['founder-home']['name'] = c['household_name']
    s['households']['oren-home']['name'] = 'Oren household'
    if 'mira-home' in s['households']: s['households']['mira-home']['name'] = 'Mira household'
    # An authored standing NPC choice, using the same finite project contract.
    s['projects']['oren-repair'] = {'household': 'oren-home', 'worker': 'oren', 'site': 'commons',
        'kind': 'repair', 'duration': MODEL['repair_seconds'], 'worked': 0, 'timber': MODEL['repair_timber'],
        'status': 'active', 'source_ref': SOURCE, 'authority': 'own-household-standing-plan'}
    if c['permission'] == 'held':
        s['grants']['founding'] = {'issuer': 'steward', 'household': 'founder-home', 'site': 'clearing',
            'rights': ['camp', 'temporary_dwelling'], 'status': 'accepted', 'active': True,
            'source_ref': SOURCE, 'accepted_ref': 'reviewed-setup:' + review_digest}
    from settlement_runtime import notice, inspect_local
    notice(s, 'founder', 0, 'setup', 'You arrive at the commons. The clearing is a five-minute walk away. '
           'Steward Elin can discuss a limited founding grant. Oren is repairing a shelter with private goods.')
    inspect_local(s, 'founder', 0, 'setup-inspection')
    world = CoreWorld(state=s)
    if c.get('offer_profile') == OFFER_PROFILE:
        world.s['communication_rules']['stock_profile'] = 'settlement_free_stock'
        world.s['communication_rules']['stock_authorities'] = {'founder-household-offer': ['founder-home']}
        from r9_runtime import grant
        grant(world, 'founder-household-offer', 'founder', ['execute_local_communication'], 0,
              OFFER_SOURCE + ':reviewed:' + review_digest)
        world.s['r9']['mandates']['founder-household-offer']['offer_scope'] = {
            'purpose': 'household-offer', 'account': 'founder-home'}
    return world
