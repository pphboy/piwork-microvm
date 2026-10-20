import json,os,pathlib,sqlite3,subprocess,sys,tomllib
def docker(*args):return subprocess.check_output(['/usr/local/bin/docker',*args],text=True).strip()
work=sys.argv[1]
volumes=json.loads(docker('volume','ls','--filter','label=piwork.work_id='+work,'--format','{{json .}}').replace('\n',',').join(['[',']']))
out={'work':work,'kernel':os.uname().release,'docker':json.loads(docker('info','--format','{"version":"{{.ServerVersion}}","driver":"{{.Driver}}","cgroupVersion":"{{.CgroupVersion}}","dataRoot":"{{.DockerRootDir}}"}')),'volumes':[],'databases':[],'containers':[]}
config=tomllib.loads(pathlib.Path('/run/docker/containerd/containerd.toml').read_text())
out['containerd']={k:config[k] for k in ['root','state']}
out['containerd']['rootBacking']=json.loads(subprocess.check_output(['findmnt','--json','--target',config['root'],'--output','TARGET,FSTYPE,SOURCE'],text=True))['filesystems'][0]
paths=['/var/lib/piwork/core']
for v in volumes:
    data=json.loads(docker('volume','inspect',v['Name'],'--format','{{json .}}'))
    out['volumes'].append({k:data[k] for k in ['Name','Driver','Mountpoint','Labels']})
    paths.append(data['Mountpoint'])
for root in paths:
    for base,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if d not in ['node_modules']]
        for name in files:
            if not name.endswith(('.sqlite','.db')):continue
            p=str(pathlib.Path(base)/name)
            c=sqlite3.connect(p,timeout=10)
            entry={'path':p,'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'journalMode':c.execute('PRAGMA journal_mode').fetchone()[0]}
            entry['backing']=json.loads(subprocess.check_output(['findmnt','--json','--target',p,'--output','TARGET,FSTYPE,SOURCE'],text=True))['filesystems'][0]
            if name=='memory.sqlite':entry['head']=c.execute('SELECT version FROM memory_head').fetchone()[0]
            if name=='work.sqlite':entry['sessions']=c.execute('SELECT count(*) FROM sessions').fetchone()[0]
            if name=='microvm.sqlite':entry['counter']=c.execute('SELECT value FROM counter').fetchone()[0]
            c.close();out['databases'].append(entry)
for cid in docker('ps','-a','--filter','label=piwork.work_id='+work,'--format','{{.ID}}').splitlines():
    # Never request Config.Env, which contains internal control credentials.
    x=json.loads(docker('inspect',cid,'--format','{"id":"{{.Id}}","image":"{{.Image}}","user":"{{.Config.User}}","ports":{{json .HostConfig.PortBindings}},"mounts":{{json .Mounts}},"labels":{{json .Config.Labels}}}'))
    out['containers'].append(x)
print(json.dumps(out,indent=2))
