Set fso = WScript.CreateObject("Scripting.FileSystemObject")

Dim WShell
Set WShell = CreateObject("WScript.Shell")
If (fso.FileExists("stroll.exe")) Then
    WShell.Run "stroll.exe --startup", 0
Else
    WShell.Run "env\Scripts\python.exe src\stroll.py --startup", 1
End If