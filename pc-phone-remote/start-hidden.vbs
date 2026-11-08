Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

pyw = "pythonw.exe"
userProfile = shell.ExpandEnvironmentStrings("%USERPROFILE%")
candidate1 = userProfile & "\AppData\Local\Python\bin\pythonw.exe"
candidate2 = userProfile & "\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"

If fso.FileExists(candidate1) Then
    pyw = """" & candidate1 & """"
ElseIf fso.FileExists(candidate2) Then
    pyw = """" & candidate2 & """"
End If

command = pyw & " """ & appDir & "\app.py"" --host 0.0.0.0 --port 8765"
shell.Run command, 0, False
