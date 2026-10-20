"""Destructive only within its explicitly named acceptance probe directory."""
import fcntl, json, os, pathlib, signal, sqlite3, subprocess, sys, time

def connection(db):
    c=sqlite3.connect(db,timeout=5)
    c.execute('PRAGMA synchronous=FULL')
    return c

def probe(root):
    root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
    result={'path':str(root)}
    try:
        p=root/'sync.txt'
        for n in range(10):
            tmp=root/'sync.tmp'
            with tmp.open('w') as f:f.write(str(n));f.flush();os.fsync(f.fileno())
            tmp.replace(p)
            d=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(d)
            finally:os.close(d)
            assert p.read_text()==str(n)
        result['fsyncRename']=True
    except Exception as e:result['fsyncRename']=type(e).__name__
    with (root/'lock').open('w') as lock:
        fcntl.lockf(lock,fcntl.LOCK_EX)
        code="import fcntl,sys;f=open(sys.argv[1],'r+');\ntry:fcntl.lockf(f,fcntl.LOCK_EX|fcntl.LOCK_NB);sys.exit(2)\nexcept BlockingIOError:sys.exit(0)"
        result['crossProcessLock']=subprocess.run([sys.executable,'-c',code,str(root/'lock')]).returncode==0
    for mode in ['DELETE','WAL']:
        db=root/('probe-'+mode+'.sqlite');out={}
        try:
            c=connection(db);out['journalMode']=c.execute('PRAGMA journal_mode='+mode).fetchone()[0]
            c.execute('CREATE TABLE IF NOT EXISTS count(n INTEGER)');c.execute('DELETE FROM count');c.execute('INSERT INTO count VALUES(0)');c.commit();c.close()
            code="import sqlite3,sys;c=sqlite3.connect(sys.argv[1],timeout=10);c.execute('PRAGMA synchronous=FULL');\nfor _ in range(25):c.execute('BEGIN IMMEDIATE');c.execute('UPDATE count SET n=n+1');c.commit()\nc.close()"
            workers=[subprocess.Popen([sys.executable,'-c',code,str(db)],stderr=subprocess.DEVNULL) for _ in range(3)]
            out['writerExitCodes']=[p.wait(timeout=40) for p in workers]
            c=connection(db);out['committedCount']=c.execute('SELECT n FROM count').fetchone()[0];c.close()
            code="import sqlite3,sys,time;c=sqlite3.connect(sys.argv[1]);c.execute('PRAGMA synchronous=FULL');c.execute('BEGIN IMMEDIATE');c.execute('UPDATE count SET n=n+1000');print('open',flush=True);time.sleep(60)"
            child=subprocess.Popen([sys.executable,'-c',code,str(db)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            assert child.stdout.readline().strip()=='open';child.kill();child.wait(timeout=10)
            c=connection(db);out['afterInterruptedTransaction']=c.execute('SELECT n FROM count').fetchone()[0];out['integrity']=c.execute('PRAGMA integrity_check').fetchone()[0];c.close()
            out['passed']=out['writerExitCodes']==[0,0,0] and out['committedCount']==75 and out['afterInterruptedTransaction']==75 and out['integrity']=='ok'
        except Exception as e:
            out['error']=type(e).__name__;out['passed']=False
            if isinstance(e,sqlite3.Error):out.update(sqliteCode=getattr(e,'sqlite_errorcode',None),sqliteName=getattr(e,'sqlite_errorname',None),detail=str(e))
        result[mode]=out
    return result

if __name__=='__main__':
    print(json.dumps([probe(p) for p in sys.argv[1:]],indent=2))
