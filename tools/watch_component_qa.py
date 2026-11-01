"""Test newly pushed component sets and retain reports outside repository source.

No Git commit or push is made. The coordinator includes reviewed QA in a versioned
unified publication. No component code is changed or merged. Candidate commits are local, disposable
assemblies, identified separately from the published Engine, App and Catalog commits.
"""
import argparse,fcntl,hashlib,io,json,os,shutil,signal,subprocess,sys,tarfile,time
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parent.parent

def now():return datetime.now(timezone.utc).isoformat()

def git(repo,*args,data=None,env=None,check=True):
 r=subprocess.run(['git','-C',str(repo),*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=90)
 if check and r.returncode:raise RuntimeError('git '+args[0]+': '+r.stderr.decode(errors='replace')[-1500:])
 return r

def tip(repo):
 git(repo,'fetch','origin','refs/heads/main:refs/remotes/origin/main')
 return git(repo,'rev-parse','refs/remotes/origin/main').stdout.decode().strip()

def extract(repo,commit,destination,prefixes=None):
 destination.mkdir(parents=True,exist_ok=True)
 args=['archive',commit]
 if prefixes:args+=['--',*prefixes]
 with tarfile.open(fileobj=io.BytesIO(git(repo,*args).stdout)) as archive:
  members=archive.getmembers()
  if len(members)>25000 or sum(m.size for m in members)>1024**3:raise RuntimeError('Oversized QA snapshot')
  for m in members:
   p=PurePosixPath(m.name)
   if p.is_absolute() or '..' in p.parts or '\\' in m.name or not(m.isfile() or m.isdir()):raise RuntimeError('Unsafe QA archive entry')
   if set(p.parts)&{'saves','trash','live','__pycache__','.git','.aws','.ssh','credentials'}:continue
   if prefixes and not any(m.name==q or m.name.startswith(q+'/') for q in prefixes):raise RuntimeError('Component path escaped selected scope')
   target=destination.joinpath(*p.parts)
   if m.isdir():target.mkdir(parents=True,exist_ok=True)
   else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(m).read())

def assemble(args,refs,run):
 candidate=run/'candidate';extract(args.joined,refs['joined'],candidate)
 qa_directory=candidate/'provenance/qa'
 retained_qa={p.relative_to(candidate):p.read_bytes() for p in qa_directory.rglob('*') if p.is_file()}
 for name in ('engine/qualification/operation_register.json','engine/OPERATION_COVERAGE.md'):
  path=candidate/name
  if path.is_file():retained_qa[Path(name)]=path.read_bytes()
 for name in ('IRGS_3_3','engine','provenance','IRGS_Web','IRGS_Catalog'):
  path=candidate/name
  if path.exists():shutil.rmtree(path)
 extract(args.engine,refs['engine'],candidate,['IRGS_3_3','engine','provenance','ROADMAP.md','CONTINUATION_STATUS.md','DEVELOPMENT_LIST.md'])
 extract(args.app,refs['app'],candidate,['IRGS_Web','Start-IRGS.cmd'])
 extract(args.catalog,refs['catalog'],candidate,['IRGS_Catalog'])
 components=json.loads((candidate/'COMPONENTS.json').read_text())
 for name in ('engine','app','catalog'):components[name]['commit']=refs[name]
 (candidate/'COMPONENTS.json').write_text(json.dumps(components,indent=2)+'\n')
 for relative,data in retained_qa.items():
  path=candidate/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
 check=subprocess.run([sys.executable,'-B','tools/verify_development.py','--refresh'],cwd=candidate,capture_output=True,text=True)
 (run/'assembly.txt').write_text(check.stdout+check.stderr)
 if check.returncode:raise RuntimeError('Assembled component source verification failed: '+(check.stdout+check.stderr)[-2000:])
 git(candidate,'init','-q');git(candidate,'config','user.name','IRGS QA');git(candidate,'config','user.email','qa@irgs.invalid')
 git(candidate,'add','.');git(candidate,'commit','-q','-m','Disposable QA assembly; Engine '+refs['engine']+' App '+refs['app']+' Catalog '+refs['catalog'])
 return candidate,git(candidate,'rev-parse','HEAD').stdout.decode().strip()

def cycle(args,state):
 refs={name:tip(getattr(args,name)) for name in ('joined','engine','app','catalog')}
 pin=git(args.app,'rev-parse',refs['app']+':Engine').stdout.decode().strip()
 catalog_pin=git(args.app,'rev-parse',refs['app']+':Catalog').stdout.decode().strip()
 signature=hashlib.sha256((ROOT/'tools/qa_irgs.py').read_bytes()+Path(__file__).read_bytes()).hexdigest()
 identity=refs['engine']+':'+refs['app']+':'+refs['catalog']+':'+signature
 state['last_checked_at_utc']=now();state['published_components']=refs
 prior=state.setdefault('runs',{}).get(identity)
 if prior and (prior.get('published_commit') or prior.get('retained_locally')):
  if prior.get('status')!='blocked' or time.time()-prior.get('attempted_at',0)<300:return False
  prior=None
 if not prior:
  run=args.storage/'runs'/str(time.time_ns());run.mkdir(parents=True)
  print(now(),'Testing Engine',refs['engine'],'App',refs['app'],'Catalog',refs['catalog'],flush=True)
  output=run/'report.json';candidate=None;candidate_commit=None
  try:
   candidate,candidate_commit=assemble(args,refs,run)
   command=[sys.executable,'-B',str(ROOT/'tools/qa_irgs.py'),'--source-root',str(candidate),'--commit',candidate_commit,'--output',str(output)]
   with (run/'runner.txt').open('w') as log:
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:code=process.wait(timeout=1800)
    except subprocess.TimeoutExpired:
     os.killpg(process.pid,signal.SIGTERM)
     try:process.wait(timeout=5)
     except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
     code=124
   if code not in (0,1) or not output.exists():raise RuntimeError('QA runner did not complete; exit '+str(code))
   report=json.loads(output.read_text())
  except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
   report={'schema_version':1,'status':'blocked','finished_at_utc':now(),'independent':{'tests_run':0,'passed':0,'failed':0,'errors':0,'skipped':0},'diagnostic':str(error),'user_saves_opened':False}
  report.update(candidate_kind='disposable_component_set_assembly',candidate_commit=candidate_commit,
   candidate_components={k:refs[k] for k in ('engine','app','catalog')},joined_template_commit=refs['joined'],
   app_declared_engine_commit=pin,app_declared_catalog_commit=catalog_pin,
   pin_matches_candidate=pin==refs['engine'] and catalog_pin==refs['catalog'],
   integrated_or_deployed_by_qa=False,mechanics_modified_by_qa=False)
  from qa_irgs import markdown as qa_markdown
  if report['status']=='blocked':body='# IRGS component QA\n\nResult: **blocked**\n\n'+report['diagnostic']+'\n'
  else:body=qa_markdown(report)
  body+='\n## Component identities\n\nEngine: `'+refs['engine']+'`\n\nApp: `'+refs['app']+'`\n\nCatalog: `'+refs['catalog']+'`\n\nThis is an isolated assembly, not an integration or deployment. App dependency matches candidate: **'+str(pin==refs['engine'] and catalog_pin==refs['catalog']).lower()+'**.\n'
  output.write_text(json.dumps(report,indent=2)+'\n');output.with_suffix('.md').write_text(body)
  prior={'report_path':str(output),'attempted_at':time.time()};state['runs'][identity]=prior
 output=Path(prior['report_path']);report=json.loads(output.read_text())
 prior.update(retained_locally=True,status=report['status'])
 state['last_local_report']={'path':str(output),'status':report['status'],
     'components':{name:refs[name] for name in ('engine','app','catalog')},
     'publication':'held_for_versioned_coordinator_review'}
 print(now(),'Retained local QA',report['status'],str(output),flush=True)
 return True


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--joined',type=Path,default=Path('/workspace/WorldWard'))
 parser.add_argument('--engine',type=Path,default=Path('/workspace/Fulcrum-Engine'))
 parser.add_argument('--app',type=Path,default=Path('/workspace/WORLDWARD-APP-WEB'))
 parser.add_argument('--catalog',type=Path,default=Path('/workspace/WorldWard-Catalog'))
 parser.add_argument('--storage',type=Path,default=Path('/workspace/irgs-cloud/component-qa'))
 parser.add_argument('--interval',type=int,default=60);parser.add_argument('--once',action='store_true')
 args=parser.parse_args()
 if args.interval<60:raise SystemExit('Use at least 60 seconds between checks')
 args.storage=args.storage.resolve()
 for name in ('joined','engine','app','catalog'):
  setattr(args,name,getattr(args,name).resolve(strict=True))
  if args.storage.is_relative_to(getattr(args,name)):raise SystemExit('Keep QA storage outside source')
 args.storage.mkdir(parents=True,exist_ok=True);state_path=args.storage/'state.json'
 with (args.storage/'watch.lock').open('w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit('A component QA watcher is already active')
  state=json.loads(state_path.read_text()) if state_path.exists() else {'runs':{}}
  print(now(),'Component QA watcher started; checking published main commits every',args.interval,'seconds',flush=True)
  while True:
   state['pid']=os.getpid()
   state_path.write_text(json.dumps(state,indent=2)+'\n')
   try:cycle(args,state);state.pop('last_error',None)
   except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
    state['last_error']={'at':now(),'message':str(error)};print(now(),'QA infrastructure error',str(error),flush=True)
   state_path.write_text(json.dumps(state,indent=2)+'\n')
   if args.once:return 2 if state.get('last_error') else 0
   time.sleep(args.interval)

if __name__=='__main__':raise SystemExit(main())
