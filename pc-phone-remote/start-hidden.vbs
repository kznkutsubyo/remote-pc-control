Set shell = CreateObject("WScript.Shell")
appDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir
command = "pythonw.exe ""app.py"" --host 0.0.0.0 --port 8765"
shell.Run command, 0, False
