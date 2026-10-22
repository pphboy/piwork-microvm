#!/usr/bin/env python3
"""Collect the native PE import closure from the pinned MinGW builder."""
import hashlib,json,pathlib,re,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'dist/qemu-windows'
SYSTEM={'kernel32.dll','user32.dll','advapi32.dll','shell32.dll','ws2_32.dll','ole32.dll','oleaut32.dll','uuid.dll','version.dll','winmm.dll','imm32.dll','comdlg32.dll','comctl32.dll','gdi32.dll','secur32.dll','crypt32.dll','bcrypt.dll','ntdll.dll','msvcrt.dll','ucrtbase.dll','setupapi.dll','iphlpapi.dll','shlwapi.dll','winspool.drv','powrprof.dll','winhvplatform.dll','winhvemulation.dll'}
def main():
    roots=[pathlib.Path('/usr/x86_64-w64-mingw32/sys-root/mingw'),pathlib.Path('/usr/lib/gcc/x86_64-w64-mingw32'),ROOT/'dist/qemu-build-windows']
    available={p.name.lower():p for root in roots for p in root.rglob('*.dll')}
    queue=[OUT/'qemu-system-x86_64.exe'];seen=set();records=[]
    while queue:
        p=queue.pop()
        if p.name.lower() in seen:continue
        seen.add(p.name.lower())
        imports=re.findall(r'DLL Name: (\S+)',subprocess.check_output(['x86_64-w64-mingw32-objdump','-p',str(p)],text=True))
        for name in imports:
            lower=name.lower()
            if lower in SYSTEM or lower.startswith(('api-ms-win-','ext-ms-win-')):continue
            if lower not in available:raise SystemExit('Unresolved native import: '+name)
            target=OUT/name
            if lower not in seen:
                target.unlink(missing_ok=True)
                shutil.copy2(available[lower],target)
            queue.append(target)
        package=subprocess.run(['rpm','-qf',str(available.get(p.name.lower(),p))],capture_output=True,text=True).stdout.strip()
        records.append({'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'imports':imports,'package':package})
    licenses=OUT/'licenses'
    if licenses.exists():shutil.rmtree(licenses)
    licenses.mkdir()
    for p in OUT.glob('*.dll'):
        if p.name.lower() not in seen:p.unlink()
    for p in pathlib.Path('/usr/share/licenses').glob('mingw*'):
        if p.is_dir():shutil.copytree(p,licenses/p.name,dirs_exist_ok=True)
    source=ROOT/'dist/qemu-source/windows/qemu-10.0.8'
    for name in ['COPYING','COPYING.LIB']:shutil.copy2(source/name,licenses/('QEMU-'+name))
    shutil.copy2(source/'subprojects/slirp/COPYRIGHT',licenses/'libslirp-COPYRIGHT')
    for name in ['README.license','BSD-2-Clause','GPL']:
        shutil.copy2(source/'subprojects/dtc'/name,licenses/('dtc-'+name))
    (OUT/'native-dependencies.json').unlink(missing_ok=True)
    (OUT/'native-dependencies.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(records,indent=2))
if __name__=='__main__':main()
