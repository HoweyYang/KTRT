' KTRT launcher (console-free fallback). Prefer the desktop shortcut KTRT.lnk.
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "C:\KTRT"
ws.Run """C:\KTRT\venv\Scripts\pythonw.exe"" ""C:\KTRT\launcher.py""", 0, False
