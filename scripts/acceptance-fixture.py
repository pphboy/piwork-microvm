#!/usr/bin/env python3
"""Start a synthetic Responses protocol fixture in the production Agent."""
import argparse,importlib.util,json,os,pathlib
root=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('guestctl',root/'scripts/guestctl.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
p=argparse.ArgumentParser();p.add_argument('--runtime',type=pathlib.Path,required=True);a=p.parse_args();info=json.loads(a.runtime.read_text())
out=pathlib.Path(os.environ.get('PIWORK_ACCEPTANCE_OUT',root/'dist/acceptance'));work=json.loads((out/'storage-result.json').read_text())['workId']
ids=g.execute(info,['/usr/local/bin/docker','ps','--filter','label=piwork.work_id='+work,'--filter','name=piwork-agent-','--format','{{.ID}}']).decode().splitlines();assert len(ids)==1
source="import fs from 'node:fs';console.log=(s)=>fs.appendFileSync('/tmp/microvm-fixture.log',s+'\\n');\n"+(root/'fixtures/responses-fixture.mjs').read_text()
g.execute(info,['/usr/local/bin/docker','exec','-d',ids[0],'node','--input-type=module','-e',source])
print('Synthetic protocol fixture started on the real Agent private loopback. No real provider.')
