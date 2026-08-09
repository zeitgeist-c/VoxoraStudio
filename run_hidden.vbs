Option Explicit

Dim shell, env, scriptDir, command
Set shell = CreateObject("WScript.Shell")
Set env = shell.Environment("Process")

scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
env("VOXORA_HIDDEN") = "1"

' 0 = pencereyi gizle, False = uygulama kapanana kadar betigi bekletme.
command = "cmd.exe /d /c """ & scriptDir & "\run.bat"""
shell.Run command, 0, False
