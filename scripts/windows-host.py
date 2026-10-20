#!/usr/bin/env python3
"""Run a native PowerShell test from the Linux build workspace (not a product dependency)."""
import base64,os,subprocess,sys
exe=os.environ.get('PIWORK_POWERSHELL','/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')
script="[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); $ProgressPreference='SilentlyContinue'; $ErrorActionPreference='Stop'\n"+sys.stdin.read()
r=subprocess.run([exe,'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
sys.stdout.buffer.write(r.stdout);raise SystemExit(r.returncode)
