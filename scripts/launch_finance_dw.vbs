Option Explicit

Const APP_URL = "http://localhost:8501/"
Const PRIMARY_PYTHON = "C:\Python314\python.exe"
Const APP_WINDOW_WIDTH = 1600
Const APP_WINDOW_HEIGHT = 980

Dim shell, fso, appDir, runtimeDir, runtimeTemp, runtimeData, runtimeDb
Dim venvPython, runtimeVenvPython, pythonExe, commandLine, startedAt, ready
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Resolve app directory
appDir = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))

' Runtime directories (temp + data)
runtimeDir = "E:\finance_dw_runtime"
runtimeData = runtimeDir & "\data"
runtimeTemp = runtimeData & "\incoming"
runtimeDb = runtimeData & "\finance_dw.db"
If Not fso.FolderExists(runtimeDir) Then fso.CreateFolder runtimeDir
If Not fso.FolderExists(runtimeTemp) Then fso.CreateFolder runtimeTemp
If Not fso.FolderExists(runtimeData) Then fso.CreateFolder runtimeData
shell.Environment("PROCESS")("TMP") = runtimeTemp
shell.Environment("PROCESS")("TEMP") = runtimeTemp
shell.Environment("PROCESS")("FINANCE_DW_DB_PATH") = runtimeDb

' Find Python
venvPython = appDir & "\.venv\Scripts\python.exe"
runtimeVenvPython = "E:\finance_dw_runtime\.venv\Scripts\python.exe"
If fso.FileExists(venvPython) Then
    pythonExe = """" & venvPython & """"
ElseIf fso.FileExists(runtimeVenvPython) Then
    pythonExe = """" & runtimeVenvPython & """"
ElseIf fso.FileExists(PRIMARY_PYTHON) Then
    pythonExe = """" & PRIMARY_PYTHON & """"
Else
    pythonExe = "python"
End If

' If server already running, just open browser
If IsReady(APP_URL) Then
    OpenApp
    WScript.Quit 0
End If

' --- Aggressive startup with instant feedback ---
shell.CurrentDirectory = appDir
commandLine = pythonExe & " -m streamlit run app.py --server.port 8501 --server.headless true"
shell.Run commandLine, 0, False

' Quick poll loop: 200ms x 50 rounds = 10s first pass, then 500ms x 40 rounds = 20s more
startedAt = Timer
ready = WaitUntilReady(APP_URL, 30000)

If ready Then
    OpenApp
Else
    ' If not ready after 30s, show popup but keep waiting in background
    If IsReady(APP_URL) Then
        OpenApp
    Else
        shell.Popup "服务器已启动，正等待响应..." & vbCrLf & APP_URL, 3, "Finance DW", 64
        If IsReady(APP_URL) Then
            OpenApp
        End If
    End If
End If


Sub OpenApp()
    shell.Run BrowserCommand(APP_URL), 1, False
End Sub


Function BrowserCommand(url)
    Dim candidates, candidate
    candidates = Array( _
        shell.ExpandEnvironmentStrings("%ProgramFiles%") & "\Microsoft\Edge\Application\msedge.exe", _
        shell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe", _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Microsoft\Edge\Application\msedge.exe", _
        shell.ExpandEnvironmentStrings("%ProgramFiles%") & "\Google\Chrome\Application\chrome.exe", _
        shell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Google\Chrome\Application\chrome.exe", _
        shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Google\Chrome\Application\chrome.exe" _
    )

    For Each candidate In candidates
        If Len(candidate) > 0 And fso.FileExists(candidate) Then
            BrowserCommand = """" & candidate & """ --app=""" & url & """ --window-size=" & APP_WINDOW_WIDTH & "," & APP_WINDOW_HEIGHT & " --window-position=80,40"
            Exit Function
        End If
    Next

    BrowserCommand = url
End Function


Function WaitUntilReady(url, timeoutMs)
    Dim startedAt
    startedAt = Timer
    ' Phase 1: quick poll 200ms x 50 (10s)
    Do While ((Timer - startedAt) * 1000) < 10000
        If IsReady(url) Then
            WaitUntilReady = True: Exit Function
        End If
        WScript.Sleep 200
    Loop
    ' Phase 2: slower poll 500ms (up to timeout)
    Do While ((Timer - startedAt) * 1000) < timeoutMs
        If IsReady(url) Then
            WaitUntilReady = True: Exit Function
        End If
        WScript.Sleep 500
    Loop
    WaitUntilReady = False
End Function


Function IsReady(url)
    On Error Resume Next
    Dim http
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.setTimeouts 500, 500, 500, 500
    http.open "GET", url, False
    http.send
    IsReady = (Err.Number = 0 And http.Status >= 200 And http.Status < 500)
    Err.Clear
    On Error GoTo 0
End Function
