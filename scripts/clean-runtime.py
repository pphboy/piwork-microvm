#!/usr/bin/env python3
"""Map private paths out of the acceptance chroot."""
import json,os,pathlib
root=pathlib.Path(__file__).resolve().parents[1]
clean=pathlib.Path(os.environ.get('PIWORK_CLEAN_ROOT',root/'dist/clean-host/root'))
installation=pathlib.Path(os.environ.get('PIWORK_TEST_INSTALL_SOURCE',clean/'state/Installation'))
files=list(installation.glob('runtime.json'))
if len(files)!=1:raise SystemExit('Expected exactly one running clean acceptance installation')
info=json.loads(files[0].read_text())
for key in ['qga','qmp']:info[key]=str(clean/info[key].lstrip('/'))
info['data']=str(installation);info['disk']=str(installation/'disks/state.qcow2')
out=pathlib.Path(os.environ.get('PIWORK_ACCEPTANCE_OUT',root/'dist/acceptance'))/'clean-runtime.json';out.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f:json.dump(info,f,indent=2)
print('Private runtime paths mapped for the Host browser and probes.')
