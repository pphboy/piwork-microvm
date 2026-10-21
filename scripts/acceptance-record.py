#!/usr/bin/env python3
"""Collect only allowlisted, secret-checked local acceptance evidence."""
import argparse,hashlib,json,pathlib,shutil
root=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--linux',type=pathlib.Path,default=root/'dist/runs/dual-ports-linux/evidence')
parser.add_argument('--windows',type=pathlib.Path,default=pathlib.Path('/mnt/c/Users/p/AppData/Local/PiworkMicroVM-0.0.9-dual-ports/evidence'))
parser.add_argument('--output',type=pathlib.Path,default=root/'openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/two-port')
parser.add_argument('--real-model-input',type=pathlib.Path,help='Private model input used only to scan evidence for credential leaks')
parser.add_argument('--require-completion',action='store_true',help='Require both real-provider restart flows and all six final-artifact fault recoveries')
args=parser.parse_args()
change=args.output;change.mkdir(parents=True,exist_ok=True)
linux=args.linux;windows=args.windows
def read_record(path):return json.loads(path.read_text(encoding='utf-8-sig'))
if args.require_completion:
 for name,source in [('linux',linux),('windows',windows)]:
  first=read_record(source/'real-model-first.json');restart=read_record(source/'real-model-restart.json')
  assert first['realProvider'] and restart['continuedAfterRestart'] and restart['history']['http']==200,name
  assert first['fileSHA256']==restart['fileSHA256'],name
  assert read_record(source/'normal-stop-final.json')['clean'],name
  for mode in ['early-exit','shutdown-timeout','launcher-kill']:
   fault=read_record(source/('fault-'+mode+'.json'))
   assert all(fault[k] for k in ['uncleanMarkerRetained','installationMetadataUnchanged','diskRetained','allOriginalWritersExited']),(name,mode)
   if mode=='shutdown-timeout':assert 118<=fault['elapsedSeconds']<=145,(name,mode)
   phase='after-'+mode
   model=read_record(source/('real-model-'+phase+'.json'))
   assert model['history']['http']==200 and model['fileSHA256']==first['fileSHA256'],(name,mode)
   inspection=source/('inspection-'+phase+'.json')
   if not inspection.exists():inspection=source/('inspection-'+phase)/'guest-runtime-inspection.json'
   dbs=read_record(inspection)['databases']
   assert len(dbs)>=4 and all(d['integrity']=='ok' and d['backing']['fstype']=='ext4' for d in dbs),(name,mode)
   assert read_record(source/('service-'+phase+'.json'))['integrity']=='ok',(name,mode)
   assert read_record(source/('persistence-'+phase+'.json'))['toolSessionHistoryHTTP']==200,(name,mode)
secrets=[]
for source in [linux,windows]:
 secrets.append(json.loads((source/'credentials.json').read_text())['password'].encode())
secrets.extend([b'microvm-acceptance-synthetic-not-a-real-key',b'synthetic-fixture-only-not-provider-key'])
if args.real_model_input:secrets.append(json.loads(args.real_model_input.read_text())['credential'].encode())
allowed=['browser-result.json','persistence-result.json','guest-runtime-inspection.json','guest-runtime-before-faults.json','guest-network.json','filesystem-probe.json','qemu-proof.json','proof-8080.json','cache-runs.json','secret-scan.json','grants-result.json','revocation-result.json','recovery-browser-result.json','fault-storage.json','fault-images.json','orphan-result.json','shutdown-timeout-result.json','early-exit-result.json','preflight-failures.json','windows-process-proof.json','window-close-result.json','native-failures.json','before-parent-kill.json','memory-result.json','concurrent.json','port-preflight.json','two-port-restart.json','two-port-failures.json']
allowed+=['native-unit-tests.json','native-process-proof.json','inspection-before-restart.json','inspection-normal-restart.json','normal-stop-first.json','normal-stop-restart.json','normal-stop-final.json','completion-secret-scan.json']
for phase in ['first','restart','after-early-exit','after-shutdown-timeout','after-launcher-kill']:
 allowed += ['real-model-'+phase+'.json','real-history-browser-'+phase+'.json','inspection-'+phase+'.json','service-'+phase+'.json','persistence-'+phase+'.json','exit-'+phase+'.json','boot-'+phase+'.log']
for mode in ['early-exit','shutdown-timeout','launcher-kill']:
 allowed += ['fault-'+mode+'.json','exit-'+mode+'.json','boot-'+mode+'.log','boot-before-'+mode+'.log']
for name,source in [('linux',linux),('windows',windows)]:
 target=change/name;target.mkdir(parents=True,exist_ok=True)
 for filename in allowed:
  path=source/filename
  if not path.exists():continue
  data=path.read_bytes();assert not any(s in data for s in secrets),str(path)
  (target/filename).write_bytes(data)
 for filename in ['quickstart-ready.png','work-ready.png','service-ready.png','service-recovered.png']:
  path=source/filename
  if path.exists():shutil.copy2(path,target/filename)
 for phase in ['first','restart','after-early-exit','after-shutdown-timeout','after-launcher-kill']:
  path=source/('real-history-'+phase+'.png')
  if path.exists():shutil.copy2(path,target/path.name)
 for phase in ['before-restart','normal-restart','after-early-exit','after-shutdown-timeout','after-launcher-kill']:
  path=source/('inspection-'+phase)/'guest-runtime-inspection.json'
  if path.exists():
   data=path.read_bytes();assert not any(s in data for s in secrets),str(path)
   (target/('inspection-'+phase+'.json')).write_bytes(data)
records=[]
for filename,platform in [('piwork-microvm','linux'),('piwork-microvm.exe','windows')]:
 path=root/'dist'/filename
 with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 manifest=json.loads((root/'dist'/('bundle-manifest-'+platform+'.json')).read_text())
 records.append({'path':'dist/'+filename,'os':platform,'arch':'amd64','size':path.stat().st_size,'sha256':digest,'manifestSha256':hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'resources':len(manifest['files'])})
history={}
for name,source in [('linux',linux),('windows',windows)]:
 p=source/'memory-result.json'
 history[name]=json.loads(p.read_text()).get('toolSessionHistoryHTTP') if p.exists() else 'not verified'
real={}
for name,source in [('linux',linux),('windows',windows)]:
 first=source/'real-model-first.json';restart=source/'real-model-restart.json'
 if first.exists() and restart.exists():
  a=json.loads(first.read_text());b=json.loads(restart.read_text())
  assert a['realProvider'] and b['continuedAfterRestart'] and a['history']['http']==b['history']['http']==200
  real[name]={'verified':True,'model':a['model'],'firstRun':a['runs']['first'],'continuedRun':b['runs']['restart'],'toolHistoryHTTP':200}
 else:real[name]={'verified':False,'reason':'No completed real-provider first/restart evidence in this evidence set'}
record={'piwork':json.loads((root/'build.lock.json').read_text())['piwork'],'release':json.loads((root/'dist/piwork/metadata.json').read_text()),'images':json.loads((root/'dist/piwork/images.json').read_text()),'artifacts':records,'distribution':'local only; no push or release','realProviderCall':real,'toolSessionHistoryHTTP':history,'network':{'forwardedEndpoints':2,'UI':{'defaultHostPort':17891,'guestPort':17891},'Core':{'defaultHostPort':17871,'guestPort':17871},'services':'same UI origin /services/...; no separate Service forwards'}}
if args.require_completion:
 record['acceptanceScope']={'freshInstallations':True,'hosts':'current Linux/KVM and native Windows 11 Home build 26200/WHPX','windowsVersionMatrixRequired':False,'secondCleanComputerRequired':False,'freshDataDirDoesNotClearHostDependenciesOrCache':True}
 record['finalFaultRecovery']={name:{mode:{'verified':True,'evidence':name+'/fault-'+mode+'.json','recoveryHistoryHTTP':200,'databaseIntegrity':'ok','databaseFilesystem':'ext4'} for mode in ['early-exit','shutdown-timeout','launcher-kill']} for name in ['linux','windows']}
(change/'artifacts.json').write_text(json.dumps(record,indent=2)+'\n')
print('Collected allowlisted evidence and final binary/source identities; no credentials copied')
