#!/usr/bin/env python3
"""Extract readable third-party license texts from the Guest rootfs, read-only.

The texts live inside rootfs.ext4; without this step they can only be read by
booting the VM. debugfs reads them without mounting the image or needing root.
"""
import argparse, hashlib, json, pathlib, shutil, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
PACKAGES='/usr/share/piwork-guest-packages.txt'
def debugfs():
    tool=shutil.which('debugfs') or ('/usr/sbin/debugfs' if pathlib.Path('/usr/sbin/debugfs').exists() else None)
    if not tool:raise SystemExit('guest-licenses: debugfs is required; install e2fsprogs')
    return tool
def read(image,tool,path):
    return subprocess.run([tool,'-R','cat '+path,str(image)],capture_output=True).stdout
def package_names(image,tool):
    """Binary package names without their architecture suffix, sorted and unique."""
    names={line.split()[0].split(':')[0] for line in read(image,tool,PACKAGES).decode('utf-8','replace').splitlines() if line.strip()}
    if not names:raise SystemExit('guest-licenses: no package list in '+str(image))
    return sorted(names)
def build_tree(root,names,out):
    """Copy one copyright file per package; record a gap instead of omitting it."""
    if out.exists():shutil.rmtree(out)
    index=[]
    for name in names:
        source=root/name/'copyright'
        record={'component':name,'package':name,'path':'guest-licenses/'+name+'/copyright'}
        if source.is_file():
            data=source.read_bytes()
            target=out/name/'copyright';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            record.update(present=True,size=len(data),sha256=hashlib.sha256(data).hexdigest())
        else:
            record.update(present=False,reason='no /usr/share/doc/'+name+'/copyright in the Guest image')
        index.append(record)
    return index
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default=str(ROOT/'dist/guest/rootfs.ext4'))
    parser.add_argument('--out',default=str(ROOT/'dist/guest/guest-licenses'))
    args=parser.parse_args();image=pathlib.Path(args.image);out=pathlib.Path(args.out);tool=debugfs()
    if not image.exists():raise SystemExit('guest-licenses: missing '+str(image))
    names=package_names(image,tool)
    with tempfile.TemporaryDirectory() as tmp:
        stage=pathlib.Path(tmp)/'doc';stage.mkdir()
        # rdump recreates the source basename and follows symlinked doc directories.
        # Ownership changes fail without root and are irrelevant here, so stderr
        # stays captured rather than printed.
        subprocess.run([tool,'-R','rdump /usr/share/doc '+str(stage),str(image)],capture_output=True)
        root=stage/'doc'
        if not any(root.rglob('copyright')):raise SystemExit('guest-licenses: no documents extracted from '+str(image))
        index=build_tree(root,names,out)
    present=sum(1 for r in index if r['present'])
    write_index(out,{'packages':len(index),'present':present,'absent':len(index)-present,'entries':index})
    print('guest-licenses:',out,'packages:',len(index),'present:',present,'absent:',len(index)-present)
def write_index(out,summary):
    out.mkdir(parents=True,exist_ok=True)
    (out/'index.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
