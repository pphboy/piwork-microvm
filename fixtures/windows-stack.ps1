param([int]$TargetPid)
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class MicrovmStack {
 [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint a,bool b,int c);
 [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenThread(uint a,bool b,int c);
 [DllImport("kernel32.dll", SetLastError=true)] static extern uint SuspendThread(IntPtr h);
 [DllImport("kernel32.dll", SetLastError=true)] static extern uint ResumeThread(IntPtr h);
 [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetThreadContext(IntPtr h,IntPtr c);
 [DllImport("kernel32.dll", SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr a,byte[] b,int s,out IntPtr read);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 public static ulong[] Capture(int pid,int tid) {
   IntPtr p=OpenProcess(0x410,false,pid),t=OpenThread(0x5a,false,tid),alloc=Marshal.AllocHGlobal(1280);
   IntPtr c=new IntPtr((alloc.ToInt64()+15)&~15L);var data=new byte[1232];Marshal.Copy(data,0,c,data.Length);Marshal.WriteInt32(c,48,0x100001);
   try {SuspendThread(t);if(!GetThreadContext(t,c))throw new Exception("context "+Marshal.GetLastWin32Error());
     ulong rip=(ulong)Marshal.ReadInt64(c,248),rsp=(ulong)Marshal.ReadInt64(c,152);byte[] stack=new byte[4096];IntPtr n;
     if(!ReadProcessMemory(p,new IntPtr((long)rsp),stack,stack.Length,out n))throw new Exception("read "+Marshal.GetLastWin32Error());
     var result=new ulong[514];result[0]=rip;result[1]=rsp;for(int i=0;i<512;i++)result[i+2]=BitConverter.ToUInt64(stack,i*8);return result;
   } finally {ResumeThread(t);CloseHandle(t);CloseHandle(p);Marshal.FreeHGlobal(alloc);}
 }
}
'@
$p=Get-Process -Id $TargetPid
$modules=@($p.Modules | ForEach-Object { @{name=$_.ModuleName;base=$_.BaseAddress.ToInt64();size=$_.ModuleMemorySize;path=$_.FileName} })
$threads=@($p.Threads | ForEach-Object { $id=$_.Id; try {@{id=$id;state=$_.ThreadState.ToString();stack=[MicrovmStack]::Capture($TargetPid,$id)}}catch{@{id=$id;error=$_.Exception.Message}} })
@{modules=$modules;threads=$threads} | ConvertTo-Json -Depth 6 -Compress
