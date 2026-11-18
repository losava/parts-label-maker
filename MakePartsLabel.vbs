Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\MakePartsLabel.bat"
WshShell.CurrentDirectory = scriptDir
WshShell.Run "cmd /k """ & batPath & """", 1, False
