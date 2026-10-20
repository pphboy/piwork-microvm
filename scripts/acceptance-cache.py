#!/usr/bin/env python3
"""Fault only the current immutable acceptance cache with its VM stopped."""
import argparse,json,os,pathlib,shutil
root=pathlib.Path(__file__).resolve().parents[1]
clean=pathlib.Path(os.environ.get('PIWORK_CLEAN_ROOT',root/'dist/clean-host/root'))
p=argparse.ArgumentParser();p.add_argument('mode',choices=['clear','corrupt']);a=p.parse_args()
assert not (clean/'state/Installation/runtime.json').exists(),'Stop the test VM first'
with (root/'dist/piwork-microvm').open('rb') as f:f.seek(-32,2);key=f.read(32).hex()
cache=clean/'cache/piwork-microvm/bundles'/key
assert cache.is_dir() and len(key)==64
if a.mode=='clear':shutil.rmtree(cache)
else:
 file=cache/'guest/kernel';file.chmod(0o644)
 with file.open('r+b') as f:b=f.read(1);f.seek(0);f.write(bytes([b[0]^255]));f.flush();os.fsync(f.fileno())
 file.chmod(0o444)
print('Owned immutable cache '+a.mode+' applied; persistent installation untouched')
