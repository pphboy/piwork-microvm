"""Allowlisted Guest identity probe, also usable by the native Windows controller."""
import json,pathlib,subprocess
run=lambda *args: subprocess.check_output(args,text=True)
core=json.loads(run('/usr/local/bin/piwork-core','--version'))
cli=json.loads(run('/usr/local/bin/piwork-cli','--version'))
expected=json.loads(pathlib.Path('/opt/piwork/images.json').read_text())
images={}
for role,record in expected.items():
 data=json.loads(run('/usr/local/bin/docker','image','inspect',record['reference']))[0]
 assert data['Id']==record['id']
 images[role]={'reference':record['reference'],'id':data['Id'],'os':data['Os'],'architecture':data['Architecture'],'labels':{k:v for k,v in data['Config']['Labels'].items() if k.startswith(('io.piwork.','piwork.','org.opencontainers.image.version','org.opencontainers.image.revision'))}}
commands=[]
for path in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
 try:args=path.read_bytes().rstrip(b'\0').decode().split('\0')
 except (OSError,UnicodeError):continue
 if args and args[0]=='/usr/local/bin/piwork-core':commands.append(args)
assert len(commands)==1
print(json.dumps({'core':core,'cli':cli,'images':images,'nativeCoreCommand':commands[0]}))
