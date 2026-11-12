"""Deterministic campaign state and experiment controls (stdlib only)."""
import argparse, hashlib, json, os, pathlib, subprocess, sys, time, uuid, fcntl, shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]; CAMP=ROOT/'campaign'
POLICY_KEYS={'allow_local','allow_slurm','partitions','cpus_max','memory_mb_max','gpus_max','wall_minutes_max','concurrency_max','attempts_max','elapsed_hours_max','storage_mb_max'}
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def atomic(path,obj):
 p=pathlib.Path(path); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+'.tmp'); t.write_text(json.dumps(obj,indent=2)+'\n'); os.replace(t,p)
def current():
 xs=sorted(p for p in CAMP.iterdir() if p.is_dir() and (p/'state.json').exists()); return xs[-1] if xs else None
def validate_policy(p):
 if set(p)!=POLICY_KEYS: raise ValueError('policy must contain exactly: '+', '.join(sorted(POLICY_KEYS)))
 for k in ('allow_local','allow_slurm'):
  if not isinstance(p[k],bool): raise ValueError(k+' must be boolean')
 for k in ('cpus_max','memory_mb_max','gpus_max','wall_minutes_max','concurrency_max','attempts_max','elapsed_hours_max','storage_mb_max'):
  if not isinstance(p[k],(int,float)) or p[k]<0: raise ValueError(k+' must be a nonnegative number')
 if not isinstance(p['partitions'],list): raise ValueError('partitions must be a list')
 if p['allow_slurm'] and not p['partitions']: raise ValueError('Slurm authorization requires explicit partitions')
 if not p['allow_local'] and not p['allow_slurm']: raise ValueError('no execution mode authorized')
 return p
def init():
 brief=(ROOT/'RESEARCH_BRIEF.md').read_text();
 if '[Question' in brief or '[Systems' in brief: raise ValueError('Brief incomplete')
 pol=json.loads(pathlib.Path('policy.json').read_text()); validate_policy(pol)
 cid=time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]; d=CAMP/cid; d.mkdir(parents=True,exist_ok=False)
 (d/'brief.snapshot.md').write_text(brief); atomic(d/'policy.json',pol); atomic(d/'state.json',{'id':cid,'status':'ready','created':time.time(),'brief_sha256':digest(brief),'attempts':0,'jobs':[]})
 (d/'experiment-ledger.jsonl').touch(); (d/'findings.md').write_text('# Findings\n'); (d/'protocol.md').write_text('# Protocol\nAgent must define questions, baseline, outcomes, controls, replication, stopping criteria and validity threats before experiments.\n'); print(d)
def verify(d):
 brief=(ROOT/'RESEARCH_BRIEF.md').read_text(); s=json.loads((d/'state.json').read_text())
 if digest(brief)!=s['brief_sha256']: raise ValueError('brief changed; preserve this campaign and initialize a new one')
 validate_policy(json.loads((d/'policy.json').read_text())); return s
def check(): print('python='+sys.version.split()[0]+' sbatch='+str(shutil.which('sbatch') is not None)+' squeue='+str(shutil.which('squeue') is not None))
def status():
 d=current()
 if not d: print('No campaign'); return
 s=verify(d); print(json.dumps({'path':str(d),'state':s,'policy':json.loads((d/'policy.json').read_text())},indent=2))
def stop():
 d=current()
 if d: (d/'STOP').touch(); print('Graceful stop requested; active jobs are not cancelled.')
 else: print('No campaign')
def report():
 d=current()
 if not d: print('No campaign'); return
 s=verify(d); rows=[json.loads(x) for x in (d/'experiment-ledger.jsonl').read_text().splitlines() if x.strip()]
 (d/'report.md').write_text('# Campaign report\n\nStatus: '+s['status']+'\n\nExperiments: '+str(len(rows))+'\n\nSee ledger, findings and per-experiment artifacts.\n'); print(d/'report.md')
def run_job(argv):
 mode,polpath,cmd=argv[0],pathlib.Path(argv[1]),argv[2:]; pol=validate_policy(json.loads(polpath.read_text()))
 if mode=='local':
  if not pol['allow_local']: raise ValueError('local execution not authorized')
  if not os.environ.get('SLURM_JOB_ID'): raise ValueError('local research execution requires an active Slurm allocation; use explicit smoke mode for tiny offline test')
  if len(cmd)==0: raise ValueError('command required')
  return subprocess.call(cmd)
 if mode=='slurm':
  if not pol['allow_slurm']: raise ValueError('Slurm submissions not authorized')
  raise ValueError('submission requires fully specified site-valid job request; this helper accepts only validated policy, not yet a signed request')
 raise ValueError('mode must be local or slurm')
def cli():
 a=argparse.ArgumentParser(); a.add_argument('command',choices=['check','init','start','status','stop','report','smoke']); ns=a.parse_args()
 if ns.command=='check': check()
 elif ns.command=='init': init()
 elif ns.command=='status': status()
 elif ns.command=='stop': stop()
 elif ns.command=='report': report()
 elif ns.command=='start': print('Foreground agent runs AGENT_INSTRUCTIONS.md; exit pauses the loop.')
 else: subprocess.run([sys.executable,str(ROOT/'examples/smoke_test/run.py')],check=True)
if __name__=='__main__': cli()
