"""Role-scoped navigation metadata and verified campaign discovery.

Visibility describes this local owner's explicit workspace, not an account or
an entitlement. A registered route grants no access to its underlying data.
"""
import copy
import json
from catalog_paths import CATALOG_ROOT

from historical_campaigns import historical_catalogue, historical_entry
from campaign_worlds import WORLD_FILES, world_listing
from campaign_portfolio import campaign_portfolio

LISTINGS_PATH = CATALOG_ROOT / 'data/campaign_listings.json'
LIFECYCLES = ('planned', 'scaffold', 'in_development', 'functional', 'deferred')


def _feature(identity, label, order, parent=None, *, roles=('player',), lifecycle='planned', backend=None, description=None):
    return {'id': identity, 'label': label, 'parentId': parent, 'route': '#/' + identity,
        'order': order, 'area': 'developer' if roles == ('developer',) else 'creator' if roles == ('creator',) else 'player',
        'lifecycle': lifecycle, 'availableTo': list(roles), 'showInDevelopment': True,
        'showInPreview': lifecycle == 'functional', 'showInRelease': lifecycle == 'functional',
        'requiredBackendCapability': backend,
        'description': description or ('Scoped record view. Action capabilities remain independently validated.' if lifecycle == 'functional'
            else 'Planned view. No operational data or action capability is supplied by this route.'),
        'dependencyIds': [parent] if parent else []}


FEATURES = [
    _feature('home', 'Home / Dashboard', 0, lifecycle='functional', description='Resume a saved playthrough or browse the campaign directory.'),
    _feature('content-library', 'Content Library', 10, lifecycle='functional', backend='api/content-library', description='Verified campaign listings and dated starting-point availability.'),
    _feature('my-campaigns', 'My Campaigns / Saves', 20, lifecycle='functional', backend='api/campaigns', description='Resume existing saves independently of catalogue membership.'),
    _feature('character-creation', 'Character Creation', 30, lifecycle='functional', backend='api/starting-options', description='Review a permitted character and starting point before an atomic new save.'),
    _feature('play', 'Play', 40, lifecycle='functional', backend='api/playthrough', description='One saved world; server-filtered views and unresolved player declarations.'),
    _feature('ai-network', 'AI Network', 50, roles=('developer',), description='Planned six-category Director network; no provider or autonomous narrator is connected.'),
    _feature('workshop', 'Campaign Workshop', 60, roles=('creator',), lifecycle='in_development', backend='api/creator/drafts/preview', description='Bounded disposable draft preview; durable playtests and broader authoring remain unavailable.'),
    _feature('marketplace', 'Marketplace / Publish', 70, roles=('creator',), description='Planned publishing and commerce; no listings, prices or balances are active.'),
    _feature('account', 'Account', 80, description='Planned account services; this installation has a local campaign owner, not hosted accounts.'),
    _feature('developer', 'Developer / Administration', 90, roles=('developer',), description='Local-owner diagnostics and planned administration; each data route remains independently guarded.'),
    _feature('creator', 'Creator tools', 91, roles=('creator',), lifecycle='functional', backend='creator_mode', description='Explicit full inspection and sourced Core event tools for the local owner.'),
    _feature('library', 'Engines & technical libraries', 92, roles=('creator',), lifecycle='functional', backend='api/catalog', description='Installed reference infrastructure, separate from playable campaign listings.'),
    _feature('historical-reference-library', 'Historical Details', 92.5, roles=('creator',), lifecycle='functional',
        backend='api/historical-reference', description='Browse the verified Catalog archive or an explicitly attached local historical ZIP. Research remains separate from live campaigns and character knowledge.'),
    _feature('trash', 'Campaign Trash', 93, lifecycle='functional', backend='api/trash', description='Recoverable saved campaigns; restore never overwrites another save.'),
]


def _children(parent, items, *, roles=('player',)):
    base = next(item['order'] for item in FEATURES if item['id'] == parent)
    for index, item in enumerate(items, 1):
        identity, label, *rest = item
        opts = rest[0] if rest else {}
        FEATURES.append(_feature(identity, label, base + index / 100, parent, roles=roles, **opts))


_children('content-library', [('hyw-detail', 'Hundred Years’ War Campaign Detail'),
    ('starting-periods', 'Starting Periods & Entry Points'), ('starting-scenarios', 'Starting Scenarios'),
    ('owned-content', 'My Library / Owned Content')])
_children('character-creation', [('choose-perspective', 'Choose Perspective'), ('existing-characters', 'Existing Characters'),
    ('existing-institutions', 'Existing Factions / Institutions'), ('identity-origins', 'Identity & Origins'),
    ('family-household', 'Family & Household'), ('wealth-responsibilities', 'Wealth & Responsibilities'),
    ('education-capabilities', 'Education & Capabilities'), ('formative-life-path', 'Formative Life Path'),
    ('adult-history', 'Adolescence / Adult History'), ('starting-career', 'Career / Service / Contracts'),
    ('starting-review', 'Starting Assets & Review'), ('confirm-begin', 'Confirm & Begin'),
    ('opening-handoff', 'Opening Scene Handoff'), ('character-templates', 'Standalone Character Templates')])
_children('play', [('story', 'Story', {'lifecycle': 'functional', 'backend': 'api/playthrough', 'description': 'Own received records and exact player intent; general adjudication and narration remain unavailable.'}),
    ('world', 'World', {'lifecycle': 'functional', 'backend': 'api/playthrough', 'description': 'Permission-filtered records from the same authoritative world.'}),
    ('chronicle', 'Chronicle', {'lifecycle': 'functional', 'backend': 'api/chronicle', 'description': 'Scoped record retrieval, search and pagination; no automatic summaries.'}),
    ('character', 'Character', {'lifecycle': 'functional', 'backend': 'api/playthrough'}),
    ('inventory', 'Inventory & Equipment', {'lifecycle': 'functional', 'backend': 'api/playthrough'}),
    ('relationships', 'Relationships & Household'), ('lineage', 'Family / Lineage / Legacy'),
    ('career', 'Career / Contracts'), ('projects', 'Projects / Research'), ('personal-journal', 'Journal / Personal Records'),
    ('reports', 'Notifications / Reports'), ('action-controls', 'Action / Time Controls'), ('saves-branches', 'Saves / Branches')])
_children('story', [('first-interaction', 'Opening / First Interaction', {'lifecycle': 'scaffold',
    'backend': 'opening_scene', 'description': 'Actor-known opening presentation and exact intent recording; the resolved interaction loop remains unavailable.'})])
_children('world', [('atlas', 'Atlas'), ('economy', 'Economy'), ('politics', 'Politics & Government'),
    ('military', 'Military & Command'), ('settlements', 'Settlements / Cities'), ('institutions', 'Institutions / Organizations'),
    ('civilization', 'Civilization Overview'), ('technology', 'Technology / Discoveries / Research')])
_children('atlas', [('atlas-layers', 'Atlas Layers'), ('atlas-search', 'Atlas Search'), ('atlas-routes', 'Atlas Routes')])
_children('economy', [(identity, label) for identity, label in [('resources', 'Resources'), ('production', 'Production'),
    ('trade', 'Trade'), ('finance', 'Finance'), ('labour', 'Labour'), ('logistics', 'Logistics')]])
_children('politics', [('diplomacy', 'Diplomacy'), ('treaties', 'Treaties'), ('political-networks', 'Political Networks')])
_children('military', [('operations', 'Operations'), ('military-supply', 'Supply'), ('mercenary-companies', 'Mercenary Companies')])
_children('settlements', [('infrastructure', 'Infrastructure'), ('construction', 'Construction'), ('maintenance', 'Maintenance')])
_children('institutions', [('governance', 'Governance'), ('institution-members', 'Members'), ('institution-assets', 'Assets'),
    ('institution-contracts', 'Contracts'), ('institution-history', 'History')])
FEATURES.append(_feature('historical-comparison', 'Historical Comparison', 40.99, 'world', roles=('creator',),
    description='Planned creator-only historical baseline comparison; never character knowledge.'))
_children('workshop', [('workshop-dashboard', 'Workshop Dashboard'), ('campaign-builder', 'Campaign Builder', {'lifecycle': 'in_development', 'backend': 'api/creator/drafts/preview', 'description': 'Creator-only data editor for the two selected Engine draft profiles; preview saves no campaign.'}),
    ('scenario-builder', 'Entry Point & Scenario Builder'), ('npc-templates', 'Character & NPC Templates'),
    ('item-templates', 'Item & Equipment Templates'), ('map-authoring', 'Geography / Map Authoring'),
    ('institution-authoring', 'Governments / Factions / Institutions'), ('technical-modules', 'Technical Content Libraries / Modules'),
    ('clone-extend', 'Templates / Clone / Extend'), ('historical-research', 'Research & Historical Data'),
    ('playtest-validation', 'Validation / Playtest', {'lifecycle': 'in_development', 'backend': 'api/creator/drafts/preview', 'description': 'Disposable actor-filtered initialization preview only; durable playtest creation remains unavailable.'}), ('versions-exports', 'Versions / Exports / Dependencies'),
    ('workshop-access', 'Workshop Access / Time / Credits / Packs')], roles=('creator',))
_children('marketplace', [('marketplace-browse', 'Marketplace Browse'), ('product-detail', 'Product Detail / Contributors'),
    ('bundles', 'Bundles / Entry-Point Upgrades'), ('merged-campaigns', 'Merged Campaigns'), ('publish', 'Publish / Submission'),
    ('submission-review', 'Submission Review / Status'), ('package-builder', 'Package Builder'),
    ('contributor-consent', 'Contributor Consent / Splits'), ('royalties', 'Royalty & Payout Dashboard'),
    ('rights-provenance', 'Rights / Attribution / Provenance')], roles=('creator',))
_children('ai-network', [('network-map', 'Spiderweb Network Map'), ('directors', 'Directors & Scopes'),
    ('specialists', 'Specialist Registry'), ('providers-models', 'Providers & Models', {'lifecycle': 'functional', 'backend': 'api/ai/status', 'description': 'Protected local operator route and readiness status. No provider request is automatic.'}), ('capability-broker', 'Capability Broker / Access'),
    ('usage-budgets', 'Usage & Budgets', {'lifecycle': 'functional', 'backend': 'api/ai/usage', 'description': 'Protected read-only Engine reservations and reported tokens. Charges remain unknown.'}), ('connections-tasks', 'Connections / Tasks'), ('events-fidelity', 'Events / Scheduler / Fidelity'),
    ('execution-traces', 'Execution Traces / Errors'), ('ai-benchmarks', 'Benchmarks / Comparisons / Budgets')], roles=('developer',))
_children('account', [('profile-settings', 'Profile / Settings'), ('licences', 'Licences & Distribution'),
    ('entitlements', 'My Purchases / Entitlements'), ('gameplay-rest', 'Gameplay Access / Rest'), ('usage-costs', 'Usage & AI Costs'),
    ('authoring-credits', 'Workshop Credits / Authoring Time'),
    ('solo-exchange', 'Solo Universal Points', {'lifecycle': 'deferred'}),
    ('solo-conversion', 'Solo Currency Conversion', {'lifecycle': 'deferred'}),
    ('solo-redemption', 'Solo Redemption Catalogue', {'lifecycle': 'deferred'}),
    ('solo-transactions', 'Solo Transaction History', {'lifecycle': 'deferred'}), ('privacy-providers', 'Privacy / Connected AI Providers')])
_children('developer', [('feature-registry', 'Feature Registry / Release Visibility', {'lifecycle': 'functional', 'backend': 'api/features'}),
    ('opening-diagnostics', 'Opening / First-Turn Diagnostics'), ('build-provenance', 'Build Provenance / Licence Verification'),
    ('system-health', 'System Status / Health'), ('state-inspector', 'Campaign State Inspector'),
    ('historical-inspector', 'Historical Source / Event Inspector'), ('network-diagnostics', 'AI Network Diagnostics'),
    ('validation-reconciliation', 'Validation / Tests / Reconciliation'), ('publication-moderation', 'Publication Moderation / Rights'),
    ('commerce-accounting', 'Commerce / Royalty Accounting'), ('migration-versioning', 'Migration & Versioning')], roles=('developer',))


def feature_registry(stage='development', *, mode='player'):
    if stage not in ('development', 'preview', 'release'):
        raise ValueError('Unknown feature visibility stage')
    if mode not in ('player', 'creator'):
        raise ValueError('Unknown presentation mode')
    roles = {'player'} if mode == 'player' else {'player', 'creator', 'developer'}
    flag = {'development': 'showInDevelopment', 'preview': 'showInPreview', 'release': 'showInRelease'}[stage]
    selected = [f for f in FEATURES if f[flag] and roles.intersection(f['availableTo'])]
    # A visible child cannot promote a hidden or unauthorized parent.
    while True:
        selected_ids = {f['id'] for f in selected}
        retained = [f for f in selected if not f['parentId'] or f['parentId'] in selected_ids]
        if len(retained) == len(selected): break
        selected = retained
    return {'schema_version': 1, 'stage': stage, 'mode': mode,
        'authorization_model': 'local_owner_creator_opt_in',
        'features': copy.deepcopy(sorted(selected, key=lambda f: (f['order'], f['id']))), 'lifecycles': list(LIFECYCLES)}


def visible_campaign_ids():
    listing = json.loads(LISTINGS_PATH.read_text(encoding='utf-8-sig'))
    ids = listing.get('visible_campaign_ids')
    if listing.get('schema_version') != 1 or not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('Campaign listing configuration is invalid')
    return ids


def content_library():
    catalogue = historical_catalogue()
    listing = json.loads(LISTINGS_PATH.read_text(encoding='utf-8-sig'))
    campaigns = []
    if catalogue['id'] in visible_campaign_ids():
        periods = []
        for period in catalogue['periods']:
            entries = []
            for entry in catalogue['entries']:
                if entry['period_id'] != period['id']: continue
                try: preview = historical_entry(entry['id'])
                except (ValueError, KeyError, TypeError, OSError): preview = {'ready': False, 'snapshot_sha256': None}
                ready = preview['ready'] is True
                scenarios = []
                if ready:
                    for scenario in preview['snapshot'].get('entity_registry_template', {}).get('scenarios', {}).values():
                        scenarios.append({'id': scenario['id'], 'title': scenario['title'], 'playable': True,
                            'ready': True, 'readiness': 'Supported starting policy; character review required'})
                for reference in listing.get('starting_scenario_references', []):
                    if reference.get('campaign_id') == catalogue['id'] and reference.get('entry_id') == entry['id']:
                        scenarios.append({key: copy.deepcopy(reference[key]) for key in ('id', 'title', 'status', 'reason') if key in reference})
                        scenarios[-1].update(playable=False, ready=False,
                            readiness=reference.get('reason', 'A verified scenario initializer is unavailable'))
                entries.append({**copy.deepcopy(entry), 'ready': ready, 'playable': ready,
                    'snapshot_sha256': preview['snapshot_sha256'] if ready else None,
                    'profile_id': 'military', 'scenario_id': catalogue['id'],
                    'scenarios': scenarios,
                    'readiness': 'Supported opening; review its historical scope and uncertainties' if ready else 'Reference only; supported opening unavailable'})
            periods.append({**copy.deepcopy(period), 'entries': entries})
        campaigns.append({key: copy.deepcopy(catalogue[key]) for key in ('id', 'title', 'period', 'status')})
        campaigns[-1].update(summary=catalogue['implementation_rule'], periods=periods,
            featured_years=copy.deepcopy(catalogue['featured_years']),
            entry_count=sum(len(p['entries']) for p in periods),
            playable_entry_count=sum(e['ready'] for p in periods for e in p['entries']), starts_via='new-campaign',
            launch_capability='reviewed_initialization_and_pending_declarations')
    campaigns.extend(world_listing(world_id) for world_id in WORLD_FILES
                     if world_id in visible_campaign_ids())
    from rise_campaigns import listing as rise_listing
    if 'rise' in visible_campaign_ids(): campaigns.append(rise_listing())
    return {'schema_version': 1, 'campaigns': campaigns, 'portfolio': campaign_portfolio(campaigns),
        'note': 'Campaign discovery excludes technical engines and libraries. General action resolution and narration remain unavailable.'}


def validate_player_creation(profile_id, scenario_id, entry_id, snapshot_sha256):
    for campaign in content_library()['campaigns']:
        for period in campaign.get('periods', []):
            for entry in period['entries']:
                if (campaign['id'] == scenario_id and entry['id'] == entry_id and entry['profile_id'] == profile_id
                        and entry['ready'] and entry['snapshot_sha256'] == snapshot_sha256):
                    return
    raise PermissionError('Player creation requires an approved campaign and its exact verified historical entry. Technical profiles require Creator workspace.')
