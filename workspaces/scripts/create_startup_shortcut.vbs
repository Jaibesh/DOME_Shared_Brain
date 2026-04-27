Set WshShell = CreateObject("WScript.Shell")
Set Shortcut = WshShell.CreateShortcut(WshShell.SpecialFolders("Startup") & "\DOME Control Center.lnk")
Shortcut.TargetPath = "C:\DOME_CORE\workspaces\START_DOME.bat"
Shortcut.WorkingDirectory = "C:\DOME_CORE\workspaces"
Shortcut.Description = "DOME 4.0 Agent Control Center"
Shortcut.WindowStyle = 1
Shortcut.Save
WScript.Echo "Startup shortcut created at: " & WshShell.SpecialFolders("Startup") & "\DOME Control Center.lnk"
