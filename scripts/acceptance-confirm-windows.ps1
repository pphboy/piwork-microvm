# Confirm only a named dialog belonging to the dedicated acceptance launcher.
param([Parameter(Mandatory=$true)][int]$ProcessId,[string]$Title='Stop Piwork?')
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class OwnedConfirmation {
 [DllImport("user32.dll")] public static extern IntPtr GetDlgItem(IntPtr h, int id);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
}
'@
$condition=[Windows.Automation.AndCondition]::new(
 [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ProcessIdProperty,$ProcessId),
 [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty,$Title))
$dialog=[Windows.Automation.AutomationElement]::RootElement.FindFirst([Windows.Automation.TreeScope]::Descendants,$condition)
if(!$dialog){throw 'Owned confirmation dialog not found'}
$button=[OwnedConfirmation]::GetDlgItem([IntPtr]$dialog.Current.NativeWindowHandle,6)
if($button -eq [IntPtr]::Zero){throw 'Yes button not found'}
$null=[OwnedConfirmation]::SendMessage($button,0x00F5,[IntPtr]::Zero,[IntPtr]::Zero)
Write-Output ('Confirmed owned dialog: '+$Title)
