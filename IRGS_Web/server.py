"""Loopback campaign host for IRGS Core 3.3. Standard library only."""
import argparse
import copy
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
from engine_paths import ENGINE_ROOT
sys.path.insert(0, str(ENGINE_ROOT / 'runtime'))
from core_world import CoreWorld, SUPPORTED_OPS
from campaign_library import initial_campaign, catalog, presentation_binding
from historical_campaigns import historical_catalogue, historical_entry
from content_library import lookup as lookup_content
from r9_runtime import frontier, grant, resolve
from irgs_reference import InvalidEvent, digest
from gameplay_views import playthrough, controlled_actor, pending_declaration, safe_result
from features import feature_registry, content_library, validate_player_creation
from campaign_worlds import world_reference
from historical_reference import HistoricalReferences
from assistance import SoloService, sync_parent


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.before_restore = None

    def path(self, key):
        if not isinstance(key, str) or len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid campaign ID')
        return self.folder / (key + '.json')

    def read(self, key):
        return json.loads(self.path(key).read_text(encoding='utf-8'))

    def write(self, record):
        path = self.path(record['id'])
        tmp = path.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)
        sync_parent(path)

    def create(self, name, profile_id='ast', *, scenario_id=None, entry_id=None, snapshot_sha256=None,
               character=None, starting_scenario_id='individual', selection_digest=None, request_id=None, creator=True):
        if not isinstance(name,str) or not name.strip() or len(name.strip()) > 100:
            raise ValueError('Use a campaign name between 1 and 100 characters')
        payload={'name':name,'profile_id':profile_id,'scenario_id':scenario_id,'entry_id':entry_id,
                 'snapshot_sha256':snapshot_sha256,'character':copy.deepcopy(character),
                 'starting_scenario_id':starting_scenario_id,'selection_digest':selection_digest}
        signature=digest(payload)
        if request_id is not None:
            if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',request_id):
                raise ValueError('A stable campaign creation request identity is required')
            key=hashlib.sha256(('IRGS-create:'+request_id).encode()).hexdigest()[:32]
            active,trashed=self.path(key),self.trash_path(key)
            existing=[p for p in (active,trashed) if p.exists()]
            if len(existing)>1:raise ValueError('Campaign identity collision; no save was changed')
            if existing:
                record=json.loads(existing[0].read_text(encoding='utf-8'))
                prior=record.get('creation_request',{})
                if prior.get('id')!=request_id or prior.get('payload_digest')!=signature:
                    raise ValueError('Creation request identity was reused with different choices')
                return {**{k:record[k] for k in ('id','name','revision')},'creation_replayed':True,
                        'status':'trashed' if existing[0]==trashed else 'active'}
        else:key=uuid.uuid4().hex
        if self.path(key).exists() or self.trash_path(key).exists():
            raise ValueError('Campaign identity collision; no save was changed')
        if not creator:
            validate_player_creation(profile_id, scenario_id, entry_id, snapshot_sha256)
        world = initial_campaign(profile_id=profile_id,campaign_id='IRGS-'+key,
                                 scenario_id=scenario_id,entry_id=entry_id,snapshot_sha256=snapshot_sha256)
        from starting_selection import initialize_player
        world=initialize_player(world,character=character,starting_scenario_id=starting_scenario_id,
                                selection_digest=selection_digest,
                                request_ref='explicit-campaign-create:'+key+(':'+request_id if request_id else ''))
        if not world.player_ids(world.s):raise ValueError('A campaign requires an explicitly selected player character')
        from opening_scene import build_opening
        opening=build_opening(world.s,world.player_ids(world.s)[0])
        if opening is not None:world.s['opening_scene']=opening
        record = {'id': key, 'name': name.strip(), 'revision': 0, 'state': world.s}
        if request_id is not None:record['creation_request']={'id':request_id,'payload_digest':signature}
        self.write(record)
        return record

    def listing(self):
        return [{k: r[k] for k in ('id', 'name', 'revision')} for r in
                (json.loads(p.read_text(encoding='utf-8')) for p in sorted(self.folder.glob('*.json')))]

    def trash_path(self, key):
        return self.folder / 'trash' / self.path(key).name

    def trash_listing(self):
        return [{k: r[k] for k in ('id', 'name', 'revision')} for r in
                (json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.folder / 'trash').glob('*.json')))]

    def delete(self, key, revision):
        record = self.read(key)
        if type(revision) is not int or revision != record['revision']:
            raise ValueError('This campaign changed in another tab. Reload before moving it to Trash.')
        destination = self.trash_path(key)
        destination.parent.mkdir(exist_ok=True)
        if destination.exists():
            raise ValueError('A campaign with this ID is already in Trash. Neither save was changed.')
        try:
            self.path(key).rename(destination)
        except OSError as err:
            raise ValueError('Could not move this campaign to Trash: ' + str(err)) from err
        return {'id': key, 'name': record['name'], 'revision': record['revision'], 'status': 'trashed'}

    def restore(self, key, revision):
        source, destination = self.trash_path(key), self.path(key)
        if destination.exists():
            raise ValueError('An active campaign already has this ID. Neither save was changed.')
        record = json.loads(source.read_text(encoding='utf-8'))
        if type(revision) is not int or revision != record['revision']:
            raise ValueError('This Trash record changed. Reload Trash before restoring it.')
        if self.before_restore is not None:
            self.before_restore(key)
        try:
            source.rename(destination)
        except OSError as err:
            raise ValueError('Could not restore this campaign: ' + str(err)) from err
        return record

    def event(self, key, revision, op, params):
        return self.events(key, revision, [{'op': op, 'params': params}], retain_unresolved=False)

    def current(self, key, revision):
        record = self.read(key)
        if type(revision) is not int or revision != record['revision']:
            raise ValueError('This campaign changed in another tab. Reload before submitting again.')
        return record, CoreWorld(state=record['state'])

    def commit(self, record, world, result):
        record['state'] = world.s
        record['revision'] += 1
        record['last_result'] = result
        self.write(record)
        return record

    def events(self, key, revision, events, retain_unresolved=True):
        record, world = self.current(key, revision)
        if not isinstance(events, list) or not 1 <= len(events) <= 16:
            raise ValueError('Submit between 1 and 16 events')
        submitted = []
        for event in events:
            op, params = event['op'], event['params']
            if op not in SUPPORTED_OPS or not isinstance(params, dict):
                raise ValueError('Unsupported event')
            scope = world.s['campaign_id']
            if params.get('campaign_id', scope) != scope:
                raise ValueError('Event belongs to another campaign')
            submitted.append({'id': 'web:' + uuid.uuid4().hex, 'at': world.s['clock'] + 1,
                              'op': op, 'params': {**params, 'campaign_id': scope}})
        result = frontier(world, submitted)
        if not retain_unresolved and result['deferred']:
            raise ValueError('; '.join(result.get('errors', {}).values()) or 'Event could not commit')
        return self.commit(record, world, result)

    def mandate(self, data):
        record, world = self.current(data['id'], data['revision'])
        operations = data['operations']
        if not isinstance(operations, list) or not operations or any(op not in (SUPPORTED_OPS|{'deny_unqualified'}) for op in operations):
            raise ValueError('Mandate rights must name supported Core or genre operations')
        grant(world, mandate_id=data['mandate_id'], actor=data['actor'], operations=operations,
              at=data.get('at', world.s['clock'] + 1), source_ref=data['source_ref'])
        return self.commit(record, world, {'mandate_id': data['mandate_id']})

    def decision(self, data):
        record, world = self.current(data['id'], data['revision'])
        result = resolve(world, decision_id=data['decision_id'], request_id=data['request_id'],
                         at=data.get('at', world.s['clock'] + 1), mandate_id=data['mandate_id'],
                         actor=data['actor'], approve=data['approve'])
        if world.s == record['state']:
            return record
        return self.commit(record, world, {'decision': result})

    def gameplay_request(self, data, *, withdrawal=False):
        record = self.read(data['id'])
        if not isinstance(data.get('actor'),str) or not data['actor']:
            raise ValueError('Explicitly select the player character making this request')
        actor = controlled_actor(record['state'], data['actor'])
        request_id = data.get('request_id')
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',request_id):
            raise ValueError('A stable declaration request identity is required')
        payload = {'campaign_id': record['id'], 'actor': actor,
                   'kind': 'withdrawal' if withdrawal else 'declaration'}
        if withdrawal:
            payload['action_request_id'] = data['action_request_id']
        else:
            declaration = data.get('declaration')
            if not isinstance(declaration,str) or not declaration.strip() or len(declaration)>10000:
                raise ValueError('Declare an attempt using between 1 and 10000 characters')
            payload['declaration'] = declaration
        signature = digest(payload)
        saved = record.get('gameplay_requests',{}).get(request_id)
        if saved is not None:
            if saved.get('campaign_id') != record['id'] or saved.get('payload_digest') != signature:
                raise ValueError('Request identity was reused with a different campaign, actor or declaration')
            # A lost acknowledgement is recovered before stale-revision checks.
            return safe_result(saved['result'])
        if not withdrawal:
            controlled_actor(record['state'], actor, required=True)
        if type(data.get('revision')) is not int or data['revision'] != record['revision']:
            raise ValueError('This campaign changed. Reload before submitting a new request.')
        if withdrawal:
            original = record.get('gameplay_requests',{}).get(payload['action_request_id'])
            if (not original or original.get('campaign_id') != record['id'] or original.get('actor') != actor
                    or original.get('kind') != 'declaration' or original.get('status') != 'pending'):
                raise ValueError('No own still-unexecuted declaration is available to withdraw')
            result = {'request_id': request_id, 'action_request_id': payload['action_request_id'],
                      'campaign_id': record['id'], 'actor': actor, 'status': 'withdrawn',
                      'revision': record['revision']+1, 'recorded_sequence': record['state']['clock'],
                      'elapsed_time': None, 'narrative': None}
            original['status'] = 'withdrawn'
            original['withdrawal_request_id'] = request_id
            world = None
        else:
            if pending_declaration(record,actor) is not None:
                raise ValueError('A declaration is awaiting resolution. Withdraw it before revising your intent.')
            world = CoreWorld(state=record['state'])
            reference = 'explicit-player-request:' + record['id'] + ':' + request_id
            event={'id':'gameplay:'+request_id,'at':world.s['clock']+1,'op':'record_player_action',
                   'params':{'campaign_id':world.s['campaign_id'],'actor':actor,'declaration':payload['declaration'],
                             'source_ref':reference,'instruction_ref':reference}}
            outcome=frontier(world,[event])
            if outcome['deferred']:
                raise ValueError('The declaration could not be recorded; no gameplay request was committed')
            result={'request_id':request_id,'campaign_id':record['id'],'actor':actor,
                    'declaration':payload['declaration'],'status':'declared_not_resolved',
                    'revision':record['revision']+1,'recorded_sequence':world.s['clock'],
                    'elapsed_time':None,'narrative':None}
        record.setdefault('gameplay_requests',{})[request_id] = {
            'campaign_id':record['id'],'actor':actor,'kind':payload['kind'],'payload':copy.deepcopy(payload),
            'payload_digest':signature,'result':copy.deepcopy(result),
            'status':'withdrawn' if withdrawal else 'pending'}
        if world is not None:
            self.commit(record,world,{'declaration_request_id':request_id})
        else:
            record['revision']+=1
            record['last_result']={'withdrawal_request_id':request_id}
            self.write(record)
        return result

    def action_result(self,key,request_id,actor_id=None):
        record=self.read(key)
        actor=controlled_actor(record['state'],actor_id)
        request=record.get('gameplay_requests',{}).get(request_id)
        if request is None:
            raise FileNotFoundError('No saved action result exists for this request')
        if request.get('campaign_id')!=key or request.get('actor')!=actor:
            raise PermissionError('This action result is not available to the selected character')
        if request['kind'] in ('process_phase', 'communication', 'shared_intent') or request.get('intent_api'):
            sync_parent(self.path(key))  # Finish a prior uncertain directory-sync before acknowledgment.
        result=safe_result(request['result'])
        if request['kind']=='declaration' and request['status']=='withdrawn':
            result.update(status='withdrawn',original_status='declared_not_resolved',
                          withdrawal_request_id=request['withdrawal_request_id'])
        return result

    def supported_action(self, data):
        """Commit a qualified action and its recovery result in one save replacement.

        This host is the single writer for a save directory. The same lock also
        protects direct callers, not only HTTP requests. No accepted identity
        or live-world mutation escapes a failed persistence attempt.
        """
        with self.lock:
            return self._supported_action(data)

    def _supported_action(self, data):
        allowed = {'id', 'revision', 'request_id', 'actor', 'kind', 'order_id', 'action_id', 'text', 'mode'}
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError('Use the supplied supported action without changing its parameters')
        kind = data.get('kind')
        if kind not in ('issue_equipment', 'scene_action'):
            raise ValueError('This action type is not supported')
        identifier = 'order_id' if kind == 'issue_equipment' else 'action_id'
        other_identifier = 'action_id' if kind == 'issue_equipment' else 'order_id'
        if other_identifier in data:
            raise ValueError('Use only the selected action’s parameters')
        if not isinstance(data.get('actor'), str) or not data['actor']:
            raise ValueError('Explicitly select the player character making this request')
        if not isinstance(data.get(identifier), str) or not data[identifier]:
            raise ValueError('Select a supplied action')
        text = data.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError('Describe the selected action using between 1 and 10000 characters')
        request_id = data.get('request_id')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', request_id):
            raise ValueError('A stable action request identity is required')
        record = self.read(data['id'])
        actor = controlled_actor(record['state'], data['actor'])
        payload = {'campaign_id': record['id'], 'actor': actor, 'kind': data['kind'],
                   identifier: data[identifier], 'text': text}
        signature = digest(payload)
        saved = record.get('gameplay_requests', {}).get(request_id)
        if saved is not None:
            if saved.get('campaign_id') != record['id'] or saved.get('payload_digest') != signature:
                raise ValueError('Request identity was reused with different action choices')
            # Retrieve the accepted result before testing the current revision,
            # existence, mandate, order status or remaining stock.
            return safe_result(saved['result'])
        controlled_actor(record['state'], actor, required=True)
        if type(data.get('revision')) is not int or data['revision'] != record['revision']:
            raise ValueError('This campaign changed. Reload before submitting a new request.')
        if pending_declaration(record, actor) is not None:
            raise ValueError('A declaration is awaiting resolution. Withdraw it before choosing another action.')
        world = CoreWorld(state=record['state'])
        from player_actions import equipment_options, execute_equipment_action
        from scene_actions import scene_options, execute_scene_action
        options = equipment_options(world.s, actor) if kind == 'issue_equipment' else scene_options(world.s, actor)
        reference = 'explicit-player-request:' + record['id'] + ':' + request_id
        choice = next((option for option in options if option[identifier] == payload[identifier]), None)
        if kind == 'scene_action' and choice is None:
            raise ValueError('This opening action is not available. Reload the campaign to review your options.')
        if choice is not None and text != choice['text']:
            raise ValueError('Use the exact listed action. To choose different words or intent, '
                             'write your own response in the declaration box.')
        try:
            execute = execute_equipment_action if kind == 'issue_equipment' else execute_scene_action
            resolved = execute(world, 'gameplay:' + request_id, actor,
                {'kind': kind, identifier: payload[identifier]}, reference)
        except (InvalidEvent, AssertionError, KeyError, TypeError, ValueError):
            # Private validation facts do not become knowledge on a failed request.
            message = ('This equipment issue could not be completed. No equipment was moved. '
                       'Reload the campaign to review your received orders.' if kind == 'issue_equipment'
                       else 'This opening action could not be accepted. No action was committed. '
                            'Reload the campaign to review your options.')
            raise ValueError(message) from None
        elapsed = ({'axis': world.s['elapsed_time']['axis'],
                    'duration_seconds': resolved['outcome']['elapsed_seconds'],
                    'total_seconds': resolved['outcome']['elapsed_total']}
                   if kind == 'scene_action' else None)
        result = safe_result({'request_id': request_id, 'campaign_id': record['id'], 'actor': actor,
            'kind': payload['kind'], 'declaration': text, 'status': resolved['status'],
            'revision': record['revision'] + 1, 'recorded_sequence': world.s['clock'],
            'elapsed_time': elapsed, 'narrative': None,
            'outcome': resolved['outcome'], 'receipt': resolved['receipt']})
        from local_presentation import receipt_presentation
        result['presentation'] = receipt_presentation(world, result, engine_presentation=resolved.get('presentation'))
        record.setdefault('gameplay_requests', {})[request_id] = {
            'campaign_id': record['id'], 'actor': actor, 'kind': payload['kind'],
            'payload': copy.deepcopy(payload), 'payload_digest': signature,
            'result': copy.deepcopy(result), 'status': resolved['status'],
            'dependencies': copy.deepcopy(resolved['dependencies'])}
        self.commit(record, world, {'action_request_id': request_id})
        return result


def make_server(port=8765, folder=None, *, reference_library=None, reference_error=None,
                reference_config=None, reference_manifest=None, reference_manifest_pin=None,
                reference_cache=None, solo_configuration=None, operator_config_path=None):
    references = HistoricalReferences(config=reference_config, manifest=reference_manifest,
        manifest_pin=reference_manifest_pin, cache=reference_cache,
        library=reference_library, error=reference_error)
    store = Store(folder or ROOT / 'saves')
    configuration_error = False
    if operator_config_path is not None:
        if solo_configuration is not None:
            raise ValueError('Choose one server-side assistance configuration')
        try:
            from operator_setup import load_operator_configuration
            solo_configuration = load_operator_configuration(operator_config_path, store.folder)
        except (ValueError, TypeError, OSError):
            configuration_error = True
    try:
        solo = SoloService(store, solo_configuration, configuration_error=configuration_error)
    except (ValueError, OSError, sqlite3.Error):
        if operator_config_path is None: raise
        solo = SoloService(store, configuration_error=True)
    except Exception as error:
        # Only Engine's bounded configuration failure is safe to degrade to offline.
        from solo_provider import CapabilityUnavailable
        if operator_config_path is None or not isinstance(error, CapabilityUnavailable): raise
        solo = SoloService(store, configuration_error=True)
    from process_bridge import ProcessService
    processes = ProcessService(store)
    from communication_bridge import CommunicationService
    communications = CommunicationService(store)
    from intent_bridge import IntentService
    intents = IntentService(store)
    token = secrets.token_urlsafe(32)
    from build_identity import running_build
    build = running_build()

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, data, content_type='application/json'):
            raw = json.dumps(data, ensure_ascii=False).encode() if content_type == 'application/json' else data
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def session(self):
            if self.headers.get('X-IRGS-Token')!=token:
                raise PermissionError('Reload the website to establish a local session')
            if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                raise PermissionError('Origin rejected')

        def creator(self,mode):
            self.session()
            if mode!='creator':
                raise PermissionError('Explicit Creator workspace access is required')

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {'error': 'Local access only'})
            path = urlparse(self.path).path
            query = parse_qs(urlparse(self.path).query)
            mode=query.get('mode',['player'])[0]
            try:
                if path == '/api/creator/drafts/options':
                    self.creator(mode)
                    from creator_preview import options
                    return self.reply(200, options())
                if path == '/api/ai/usage':
                    self.creator(mode)
                    from ai_usage import usage_snapshot
                    return self.reply(200, usage_snapshot(getattr(solo, 'ledger', None),
                        limit=int(query.get('limit', ['25'])[0])))
                if path == '/api/ai/status':
                    self.session()
                    if mode == 'creator':
                        self.creator(mode)
                    return self.reply(200, solo.status(developer=mode == 'creator'))
                if path.startswith('/api/ai/proposal-result/'):
                    self.session()
                    parts = path.strip('/').split('/')
                    if len(parts) != 5:
                        raise ValueError('Invalid proposal-result path')
                    return self.reply(200, solo.propose({'id': parts[3], 'request_id': parts[4],
                        'actor': query.get('actor_id', [None])[0]}, lookup=True))
                if path in ('/api/historical-reference', '/api/historical-reference/search', '/api/historical-reference/record'):
                    self.creator(mode)
                    if path == '/api/historical-reference':
                        result = references.status()
                    elif path.endswith('/search'):
                        result = references.read('search', query.get('collection', ['chronology'])[0],
                            query.get('q', [''])[0], offset=int(query.get('offset', ['0'])[0]),
                            limit=int(query.get('limit', ['20'])[0]))
                    else:
                        result = references.read('record', query.get('collection', [''])[0],
                            int(query.get('row', ['0'])[0]))
                    return self.reply(200, result)
                with store.lock:
                    if path.startswith('/api/playthrough/'):
                        self.session()
                        if mode=='creator':self.creator(mode)
                        projection = playthrough(store.read(path.rsplit('/',1)[1]),
                            query.get('actor_id',[None])[0],mode=mode)
                        record = store.read(path.rsplit('/', 1)[1])
                        projection['assistance'] = solo.status(record=record, actor=projection['actor_id'])
                        projection['process_control'] = processes.view(record, projection['actor_id']) if projection['character_available'] else {'schema_version': 1, 'processes': [], 'start_available': False, 'view_token': None}
                        projection['communication_control'] = communications.view(record,
                            projection['actor_id'] if projection['character_available'] else None)
                        projection['intent_control'] = intents.view(record,
                            projection['actor_id'] if projection['character_available'] else None)
                        from start_preview import capability_summary
                        projection['play_readiness'] = capability_summary(projection,
                            projection['process_control'].get('start_options', []), projection['communication_control'])
                        return self.reply(200, projection)
                    if path.startswith('/api/communication/received/'):
                        self.session()
                        parts = path.strip('/').split('/')
                        if len(parts) != 5:
                            raise ValueError('Invalid communication record path')
                        return self.reply(200, communications.received(store.read(parts[3]),
                            query.get('actor_id', [None])[0], parts[4]))
                    if path == '/api/starting-preview':
                        self.session()
                        if mode == 'creator':
                            self.creator(mode)
                        elif mode == 'player':
                            validate_player_creation(query.get('profile_id', ['ast'])[0],
                                query.get('scenario_id', [None])[0], query.get('entry_id', [None])[0],
                                query.get('snapshot_sha256', [None])[0])
                        else:
                            raise ValueError('Unknown presentation mode')
                        if any(len(values) != 1 for values in query.values()):
                            raise ValueError('Starting preview fields must be unique')
                        from start_preview import preview_start
                        return self.reply(200, preview_start({key: values[0] for key, values in query.items()}))
                    if path=='/api/rise/templates':
                        self.session()
                        from settlement_setup import templates
                        return self.reply(200,templates())
                    if path=='/api/features':
                        self.session()
                        if mode=='creator':self.creator(mode)
                        return self.reply(200,feature_registry(query.get('stage',['development'])[0],mode=mode))
                    if path=='/api/content-library':
                        self.session()
                        return self.reply(200,content_library())
                    if path.startswith('/api/campaign-world/'):
                        self.session()
                        return self.reply(200,world_reference(path.removeprefix('/api/campaign-world/')))
                    if path=='/api/historical-baseline':
                        self.creator(mode)
                        from historical_plans import baseline_view
                        return self.reply(200,baseline_view())
                    if path.startswith('/api/historical-plans/'):
                        self.creator(mode)
                        from historical_plans import campaign_plan_view
                        return self.reply(200,campaign_plan_view(store.read(path.rsplit('/',1)[1])['state']))
                    if path=='/api/starting-options':
                        self.session()
                        from starting_selection import starting_options
                        custom=query.get('custom_year',[None])[0]
                        return self.reply(200,starting_options(
                            profile_id=query.get('profile_id',['ast'])[0],
                            scenario_id=query.get('scenario_id',[None])[0],
                            entry_id=query.get('entry_id',[None])[0],
                            snapshot_sha256=query.get('snapshot_sha256',[None])[0],
                            starting_scenario_id=query.get('starting_scenario_id',['individual'])[0],
                            custom_year=None if custom in (None,'') else int(custom)))
                    if path.startswith('/api/availability/'):
                        self.session()
                        if mode not in ('player','creator'):raise ValueError('Unknown presentation mode')
                        if mode=='creator':self.creator(mode)
                        record=store.read(path.rsplit('/',1)[1])
                        projection=playthrough(record,query.get('actor_id',[None])[0],mode=mode)
                        registry=record['state'].get('entity_registry')
                        scenario=query.get('starting_scenario_id',['individual'])[0]
                        if registry is None:
                            return self.reply(200,{'available':False,'status':'unavailable','mode':mode,
                                'scenario_id':scenario,'factions':[],'characters':[],
                                'reason':'This playthrough has no dated entity registry. Inspection does not migrate existing saves.'})
                        if 'at' in query or 'custom_year' in query:
                            raise ValueError('Live availability uses only the committed playthrough date')
                        from temporal_registry import available_entities
                        result=available_entities(registry,scenario_id=scenario)
                        if mode=='player':
                            visible=result
                            known={a['id'] for a in projection['known_actors']}
                            fields={'id','name','category','exists','participation','eligible'}
                            result={key:copy.deepcopy(value) for key,value in result.items()
                                    if key in ('as_of','axis','scenario_id','status')}
                            for kind in ('factions','characters'):
                                result[kind]=[{k:copy.deepcopy(v) for k,v in entity.items() if k in fields}
                                              for entity in visible.get(kind,[]) if entity.get('id') in known]
                        return self.reply(200,{**result,'available':True,'mode':mode,'source':'live_playthrough_registry'})
                    if path.startswith('/api/action-result/'):
                        self.session()
                        parts=path.strip('/').split('/')
                        if len(parts)!=4:raise ValueError('Invalid action-result path')
                        return self.reply(200,store.action_result(parts[2],parts[3],query.get('actor_id',[None])[0]))
                    if path.startswith('/api/chronicle/'):
                        self.session()
                        if mode=='creator':self.creator(mode)
                        record=store.read(path.rsplit('/',1)[1])
                        projection=playthrough(record,query.get('actor_id',[None])[0],mode=mode)
                        from history_views import build_chronicle
                        return self.reply(200,build_chronicle(projection['chronicle'],query.get('q',[None])[0],
                            scope={'campaign_id':record['id'],'actor_id':projection['actor_id'],'mode':mode},
                            area=query.get('area',['timeline'])[0],limit=int(query.get('limit',['30'])[0]),
                            cursor=query.get('cursor',[None])[0]))
                    if path == '/api/catalog':
                        if mode == 'creator':
                            self.creator(mode)
                            return self.reply(200, catalog())
                        core = catalog()['core']
                        return self.reply(200, {'core': {key: core[key] for key in
                            ('id', 'version', 'single_world_per_campaign')}})
                    if path == '/api/historical-campaigns':
                        return self.reply(200, historical_catalogue())
                    if path.startswith('/api/historical-entry/'):
                        return self.reply(200, historical_entry(path.rsplit('/', 1)[1]))
                    if path == '/api/content':
                        query = parse_qs(urlparse(self.path).query)
                        return self.reply(200, lookup_content(query.get('library',[''])[0],
                            query.get('q',[''])[0], int(query.get('limit',['30'])[0])))
                    if path == '/api/campaigns':
                        return self.reply(200, {'campaigns': store.listing(), 'token': token, 'build': build})
                    if path == '/api/trash':
                        return self.reply(200, {'campaigns': store.trash_listing()})
                    if path.startswith('/api/campaign/'):
                        self.creator(mode)
                        return self.reply(200, store.read(path.rsplit('/', 1)[1]))
                    if path.startswith('/api/binding/'):
                        self.creator(mode)
                        return self.reply(200, presentation_binding(store.read(path.rsplit('/', 1)[1])['state']))
                files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/voyage.svg': ('voyage.svg', 'image/svg+xml'), '/rise.js': ('rise.js', 'text/javascript'), '/catalogue.js': ('catalogue.js', 'text/javascript'), '/solo.js': ('solo.js', 'text/javascript'), '/processes.js': ('processes.js', 'text/javascript'), '/responses.data.js': ('responses.data.js', 'text/javascript'), '/responses.js': ('responses.js', 'text/javascript'), '/routine.js': ('routine.js', 'text/javascript'), '/themes.js': ('themes.js', 'text/javascript'), '/themes.css': ('themes.css', 'text/css')}
                files.update({'/creator.js': ('creator.js', 'text/javascript'), '/communications.js': ('communications.js', 'text/javascript'), '/intents.js': ('intents.js', 'text/javascript'), '/preview.js': ('preview.js', 'text/javascript'),
                    '/preview.css': ('preview.css', 'text/css'), '/fonts.css': ('fonts.css', 'text/css'),
                    '/historical-landscape.jpg': ('historical-landscape.jpg', 'image/jpeg')})
                for font in ('newsreader', 'fraunces', 'instrument-sans', 'ibm-plex-mono', 'im-fell-english', 'im-fell-english-sc'):
                    name = font + '-latin.woff2'
                    files['/' + name] = (name, 'font/woff2')
                if path not in files:
                    return self.reply(404, {'error': 'Not found'})
                name, mime = files[path]
                self.reply(200, (ROOT / 'static' / name).read_bytes(), mime)
            except FileNotFoundError:
                if path in ('/api/starting-options', '/api/starting-preview'):
                    return self.reply(503, {'error': 'The selected starting source is unavailable. No campaign was created. Retry review when its source is available.'})
                self.reply(404, {'error': 'No saved action result exists for this request'
                                      if path.startswith('/api/action-result/') else 'Campaign not found'})
            except sqlite3.Error:
                self.reply(503, {'error': 'Assistance accounting is temporarily unavailable. Refresh its saved records later.'})
            except PermissionError as err:
                self.reply(403, {'error':str(err)})
            except ValueError as err:
                self.reply(400, {'error': str(err)})
            except OSError:
                self.reply(503, {'error': 'Saved records are temporarily unavailable. Recover the original request when storage is available.'})

        def do_POST(self):
            if not self.valid_host() or self.headers.get('X-IRGS-Token') != token:
                return self.reply(403, {'error': 'Reload the website to establish a local session'})
            if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                return self.reply(403, {'error': 'Origin rejected'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 100000:
                    raise ValueError('Request is empty or too large')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError('Submit a JSON object')
                path=urlparse(self.path).path
                mode=data.get('mode',parse_qs(urlparse(self.path).query).get('mode',['player'])[0])
                if path in ('/api/ai/proposal', '/api/ai/accept', '/api/ai/cancel'):
                    operation = {'/api/ai/proposal': solo.propose, '/api/ai/accept': solo.accept,
                                 '/api/ai/cancel': solo.cancel}[path]
                    result = operation(data)
                    if path == '/api/ai/accept' and result.get('status') == 'unavailable':
                        return self.reply(422, {**result, 'error': result['message']})
                    return self.reply(200, result)
                with store.lock:
                    if path in ('/api/event','/api/frontier','/api/events','/api/mandate','/api/resolve','/api/fork'):
                        self.creator(mode)
                    if path == '/api/creator/drafts/preview':
                        self.creator(mode)
                        if set(data) - {'draft', 'options_digest', 'mode'} or not {'draft', 'options_digest'} <= set(data):
                            raise ValueError('Submit only the selected draft and source review')
                        from creator_preview import preview
                        result = preview(data['draft'], data['options_digest'])
                    elif path == '/api/rise/preview':
                        from settlement_setup import preview
                        result=preview(data.get('choices'))
                    elif path == '/api/rise/create':
                        from rise_campaigns import create
                        result=create(store,data)
                    elif path == '/api/rise/action':
                        from rise_campaigns import action
                        result=action(store,data)
                    elif path in ('/api/process/prepare', '/api/process/execute', '/api/process/status'):
                        operation = {'/api/process/prepare': processes.prepare, '/api/process/execute': processes.execute,
                                     '/api/process/status': processes.status}[path]
                        result = operation(data)
                    elif path in ('/api/communication/prepare', '/api/communication/intent/prepare', '/api/communication/execute', '/api/communication/status'):
                        operation = {'/api/communication/prepare': communications.prepare,
                                     '/api/communication/intent/prepare': communications.prepare_supported,
                                     '/api/communication/execute': communications.execute,
                                     '/api/communication/status': communications.status}[path]
                        result = operation(data)
                    elif path in ('/api/intent/prepare', '/api/intent/execute', '/api/intent/status'):
                        operation = {'/api/intent/prepare': intents.prepare,
                                     '/api/intent/execute': intents.execute,
                                     '/api/intent/status': intents.status}[path]
                        result = operation(data)
                    elif path == '/api/declaration':
                        result=store.gameplay_request(data)
                    elif path == '/api/action':
                        result=store.supported_action(data)
                    elif path == '/api/withdraw-declaration':
                        result=store.gameplay_request(data,withdrawal=True)
                    elif path == '/api/time-advance':
                        projection=playthrough(store.read(data['id']),data.get('actor'))
                        return self.reply(422,{'error':'Automatic time advancement and action resolution are unavailable',
                            'status':'unavailable','revision':projection['revision'],'capabilities':projection['capabilities']})
                    elif path == '/api/create':
                        result = store.create(data['name'], data.get('profile_id', 'ast'),
                                              scenario_id=data.get('scenario_id'),entry_id=data.get('entry_id'),
                                              snapshot_sha256=data.get('snapshot_sha256'),character=data.get('character'),
                                              starting_scenario_id=data.get('starting_scenario_id','individual'),
                                              selection_digest=data.get('selection_digest'),request_id=data.get('request_id'),
                                              creator=mode=='creator')
                        if mode!='creator':result={k:result[k] for k in ('id','name','revision','creation_replayed','status') if k in result}
                    elif path == '/api/event':
                        result = store.event(data['id'], data['revision'], data['op'], data['params'])
                    elif path in ('/api/frontier', '/api/events'):
                        result = store.events(data['id'], data['revision'], data['events'])
                    elif path == '/api/mandate':
                        result = store.mandate(data)
                    elif path == '/api/resolve':
                        result = store.decision(data)
                    elif path == '/api/delete':
                        result = store.delete(data['id'], data['revision'])
                    elif path == '/api/restore':
                        result = store.restore(data['id'], data['revision'])
                        if mode!='creator':result={k:result[k] for k in ('id','name','revision')}
                    elif path == '/api/fork':
                        original = store.read(data['id'])
                        key=uuid.uuid4().hex
                        result = {**original, 'id': key, 'name': original['name'][:85] + ' (branch)'}
                        result['state']['fork_origin']={'save_id':original['id'],'campaign_id':original['state']['campaign_id'],'revision':original['revision']}
                        result['state']['campaign_id']='IRGS-'+key
                        if 'historical_planning' in result['state']:
                            from historical_plans import fork_plan_reference
                            result['state']['historical_planning']=fork_plan_reference(result['state']['historical_planning'],
                                result['state']['campaign_id'],result['state']['fork_origin']['campaign_id'])
                        store.write(result)
                    else:
                        return self.reply(404, {'error': 'Not found'})
                self.reply(200, result)
            except PermissionError as err:
                self.reply(403,{'error':str(err)})
            except (InvalidEvent, ValueError, TypeError, KeyError, AssertionError, FileNotFoundError) as err:
                self.reply(400, {'error': str(err) or 'The engine rejected this event. Check the required references and values.'})
            except OSError:
                self.reply(503, {'error':'The save could not be persisted. Recover the request result or retry with the same request identity.'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    original_close = server.server_close
    def close():
        solo.close()
        original_close()
    server.server_close = close
    return server


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('IRGS requires Python validation: do not launch with -O.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--reference-config', type=Path, default=ROOT / 'cache/reference_sources.json')
    parser.add_argument('--operator-config', type=Path, default=os.environ.get('IRGS_OPERATOR_CONFIG'))
    parser.add_argument('--check-operator-config', action='store_true')
    args = parser.parse_args()
    if args.check_operator_config:
        try:
            if args.operator_config is None: raise ValueError('No configuration selected')
            from operator_setup import load_operator_configuration
            load_operator_configuration(args.operator_config, ROOT / 'saves')
        except (ValueError, TypeError, OSError):
            raise SystemExit('Operator configuration is unavailable or invalid; no provider request was made.') from None
        print('Operator profile passed local route and limit validation. No provider request was made; credentials, ledger and account access were not checked.')
        raise SystemExit(0)
    from release_integrity import verify_release
    verify_release()
    from app_integrity import verify_app
    verify_app()
    from catalog_paths import verify_catalog
    verify_catalog()
    server = make_server(args.port, reference_config=args.reference_config, operator_config_path=args.operator_config)
    print(f'IRGS ready at http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
