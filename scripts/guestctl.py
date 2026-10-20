#!/usr/bin/env python3
"""Development/acceptance client for a launcher's private QGA/QMP sockets."""
import argparse, base64, json, os, pathlib, socket, time, uuid

def connect_unix(sock,path):
    # Host-side test directories can exceed sockaddr_un's 108-byte limit even
    # though the launcher's in-chroot socket path is short. Resolve its parent
    # through a live directory descriptor; never move or expose the socket.
    if len(os.fsencode(path))<104:
        sock.connect(path)
    else:
        fd=os.open(pathlib.Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
        try:sock.connect('/proc/self/fd/'+str(fd)+'/'+pathlib.Path(path).name)
        finally:os.close(fd)

def rpc(path, command, args=None, qmp=False):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(12);connect_unix(s,path)
        f=s.makefile('rwb',buffering=0)
        pending=None
        def send(cmd,arguments=None):
            nonlocal pending
            pending=uuid.uuid4().hex
            d={'execute':cmd,'id':pending}
            if arguments is not None:d['arguments']=arguments
            f.write(json.dumps(d).encode()+b'\n')
        def receive():
            while True:
                r=json.loads(f.readline())
                if r.get('id')!=pending:continue
                if 'error' in r:raise RuntimeError('Private Guest command failed: '+r['error'].get('class','unknown'))
                if 'return' in r:return r['return']
        if qmp:
            json.loads(f.readline());send('qmp_capabilities');receive()
        send(command,args)
        return receive()

def execute(info,args):
    p=rpc(info['qga'],'guest-exec',{'path':args[0],'arg':args[1:],'capture-output':True})['pid']
    while True:
        r=rpc(info['qga'],'guest-exec-status',{'pid':p})
        if r.get('exited'):
            if r.get('exitcode',0)!=0 or r.get('signal',0):raise RuntimeError('Guest command exit failure')
            return base64.b64decode(r.get('out-data',''))
        time.sleep(.15)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--runtime',type=pathlib.Path,required=True)
    p.add_argument('--qmp',action='store_true')
    p.add_argument('--exec',dest='execute',action='store_true')
    p.add_argument('--save',type=pathlib.Path)
    p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args();info=json.loads(a.runtime.read_text())
    if a.execute:out=execute(info,a.command)
    else:
        r=rpc(info['qmp' if a.qmp else 'qga'],a.command[0],json.loads(a.command[1]) if len(a.command)>1 else None,a.qmp)
        out=(json.dumps(r,indent=2)+'\n').encode()
    if a.save:
        import os
        fd=os.open(a.save,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'wb') as f:f.write(out)
    else:
        import sys
        sys.stdout.buffer.write(out)
if __name__=='__main__':main()
