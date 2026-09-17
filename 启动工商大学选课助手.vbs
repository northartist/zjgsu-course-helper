' ZJGSU Course Helper - silent launcher (starts the GUI without a console window).
' Lookup order for the interpreter:
'   1) environment variable ZJGSU_PYTHONW (full path to pythonw.exe)
'   2) pythonw.exe found on PATH
'   3) pyw.exe (Windows Python launcher) found on PATH
'   4) plain "pythonw.exe" (let Windows resolve it)
' Tip: if the GUI does not show up, run "python zjgsu_launcher.py" in a console to see the error.
Option Explicit
Dim WshShell, Fso, appDir, script, pythonw
Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")
appDir = Fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = appDir
script = Fso.BuildPath(appDir, "zjgsu_launcher.py")

pythonw = WshShell.ExpandEnvironmentStrings("%ZJGSU_PYTHONW%")
If pythonw = "%ZJGSU_PYTHONW%" Then pythonw = ""
If pythonw = "" Then pythonw = FindExe("pythonw.exe")
If pythonw = "" Then pythonw = FindExe("pyw.exe")
If pythonw = "" Then pythonw = "pythonw.exe"

WshShell.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & script & Chr(34), 0, False

Function FindExe(name)
    Dim exec, text, lines
    On Error Resume Next
    Set exec = WshShell.Exec("cmd /c where " & name)
    text = exec.StdOut.ReadAll()
    On Error GoTo 0
    text = Replace(text, Chr(13), "")
    If Len(text) > 0 Then
        lines = Split(text, Chr(10))
        FindExe = Trim(lines(0))
    Else
        FindExe = ""
    End If
End Function
