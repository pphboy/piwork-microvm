#!/usr/bin/env python3
"""Import the locked official release or build Piwork from source, without publishing."""
import argparse, base64, json, os, pathlib, subprocess
import piwork_release
from source import source_path, verify, input_mode, LockError

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT/'build.lock.json').read_text())
SRC = source_path()
OUT = ROOT/'dist/piwork'

def call(args, **kw):
    subprocess.run([str(x) for x in args], check=True, **kw)

def capture(args, **kw):
    return subprocess.check_output([str(x) for x in args], text=True, **kw).strip()

def build_from_source():
    """Existing source path: npm, upstream Go and production image builds."""
    verify(SRC, lock=LOCK)
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT/'dist/guest').mkdir(parents=True, exist_ok=True)
    if capture(['go','env','GOVERSION']) != LOCK['go']:
        raise SystemExit('Build requires '+LOCK['go'])
    node=['docker','run','--rm','--user',f'{os.getuid()}:{os.getgid()}',
          '-v',f'{SRC}:/source','-w','/source',LOCK['nodeImage']]
    call(node+['node','--version'])
    if not (SRC/'node_modules/typescript').exists():
        call(node+['npm','ci','--ignore-scripts'])
    call(node+['npm','run','build','-w','@piwork/contracts','-w','@piwork/work-store',
               '-w','@piwork/pi-adapter','-w','@piwork/pi-package','-w','@piwork/agentd',
               '-w','@piwork/desktop-webui','-w','@piwork/console-webui'])
    environment=os.environ.copy()
    environment.update(PIWORK_COMMIT=LOCK['piwork']['commit'],
        PIWORK_MODIFIED=str(bool(capture(['git','status','--porcelain'],cwd=SRC))).lower(),
        PIWORK_RELEASE_REGISTRY='docker.io/piwork-microvm-local')
    # Metadata is produced by the existing release code in the pinned Node runtime.
    nodeenv=node[:3]+sum((['-e',k+'='+environment[k]] for k in
        ('PIWORK_COMMIT','PIWORK_MODIFIED','PIWORK_RELEASE_REGISTRY')),[])+node[3:]
    call(nodeenv+['node','scripts/build-docker-release.mjs','metadata','dist/microvm-meta'])
    meta=json.loads((SRC/'dist/microvm-meta/metadata.json').read_text())
    common=['--build-arg',f'GO_BUILDER_IMAGE={LOCK["goImage"]}',
            '--build-arg',f'PIWORK_COMMIT={meta["sourceCommit"]}',
            '--build-arg',f'PIWORK_VERSION={meta["releaseVersion"]}',
            '--build-arg',f'PIWORK_MODIFIED={str(meta["sourceModified"]).lower()}',
            '--build-arg',f'PIWORK_DIRTY={str(meta["sourceModified"]).lower()}',
            '--build-arg',f'PIWORK_SOURCE_INPUT_HASH={meta["sourceInputHash"]}']
    image_records={}
    for role, dockerfile in [('agent','Dockerfile.agentd'),('fileHelper','Dockerfile.file-helper.native'),
                              ('snapshotHelper','Dockerfile.snapshot-helper.native')]:
        rendered=(SRC/dockerfile).read_text().replace('node:24-bookworm-slim',LOCK['nodeImage'])
        recipe=OUT/dockerfile
        recipe.write_text(rendered)
        args=['docker','build','-f',recipe,'-t',meta['images'][role]]+common
        if role=='agent': args+=['--target','production']
        call(args+[SRC])
        record=json.loads(capture(['docker','image','inspect',meta['images'][role]]))[0]
        if (record['Os'],record['Architecture'])!=('linux','amd64'):
            raise SystemExit('Wrong image platform')
        for key,value in [('org.opencontainers.image.revision',meta['sourceCommit']),
                          ('io.piwork.source.input-sha256',meta['sourceInputHash'])]:
            assert record['Config']['Labels'][key]==value,(role,key)
        image_records[role]={'reference':meta['images'][role],'id':record['Id']}
    deps={k:meta['images']['agent' if k=='packageHelper' else k]
          for k in ('agent','packageHelper','fileHelper','snapshotHelper')}
    encoded=base64.b64encode(json.dumps(deps,separators=(',',':')).encode()).decode().rstrip('=')
    flags=(SRC/'dist/microvm-meta/core.ldflags').read_text().strip()
    assert '-X piwork/internal/distribution.EncodedImages='+encoded in flags
    (OUT/'bin').mkdir(exist_ok=True)
    env=os.environ.copy();env.update(CGO_ENABLED='0',GOTOOLCHAIN='local',GOMAXPROCS='4',GOOS='linux',GOARCH='amd64')
    call(['go','build','-mod=readonly','-trimpath','-buildvcs=true','-ldflags',flags,
          '-o',OUT/'bin','./cmd/piwork-core','./cmd/piwork-cli'],cwd=SRC,env=env)
    call([OUT/'bin/piwork-core','--help'])
    call(['docker','save','-o',ROOT/'dist/guest/images.tar',*[v['reference'] for v in image_records.values()]])
    (OUT/'images.json').write_text(json.dumps(image_records,indent=2)+'\n')
    (OUT/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    (OUT/'build-mode.json').write_text(json.dumps({'inputMode':'source',
        'commit':LOCK['piwork']['commit']},indent=2)+'\n')
    print('Piwork production binaries and images built:',meta['releaseId'])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-build',action='store_true',
                   help='explicitly compile the locked commit instead of importing the official release')
    a=p.parse_args()
    try:
        mode=input_mode(LOCK)
    except LockError as err:
        raise SystemExit(str(err))
    if mode=='official-release' and not a.source_build:
        try:
            summary=piwork_release.check_prepared(LOCK)
            print('Piwork official release already verified; reusing preparation for',summary['tag'])
            return
        except piwork_release.ReleaseError:
            pass
        record=piwork_release.prepare_lock(LOCK)
        print('Piwork official release prepared:',record['version'],'build commit',record['buildCommit'])
        return
    build_from_source()

if __name__=='__main__': main()
