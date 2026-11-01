# End-to-end check of the Windows build: real global hook, real SendInput.
#
# WARNING: this briefly takes the foreground (about 8 seconds). Do not run it
# while playing a fullscreen game or during a call.
#
# What it does:
#   1. stops any running Lado, starts builds with LADO_QA_ACCEPT_INJECTED=1;
#   2. opens LadoQaPad.exe (a plain Win32 text field);
#   3. types a wrong-layout word plus Space with SendInput;
#   4. expects the automatic correction;
#   5. presses Shift twice and expects the manual reversal;
#   6. repeats the typing in a real password field and expects no correction.
#
# The environment variable only exists for this QA process; a normal Lado
# session ignores all injected input. The pad writes its own text to a report
# file, so password fields can be read without cross-process WM_GETTEXT.

param(
    [string]$LadoPath = (Join-Path $PSScriptRoot '..\build\Lado.exe'),
    [string]$PadPath = (Join-Path $PSScriptRoot '..\build\LadoQaPad.exe')
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Threading;

public static class Qa
{
    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct HARDWAREINPUT
    {
        public uint uMsg;
        public ushort wParamL;
        public ushort wParamH;
    }

    [StructLayout(LayoutKind.Explicit)]
    public struct INPUTUNION
    {
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT
    {
        public uint type;
        public INPUTUNION u;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, INPUT[] inputs, int size);

    [DllImport("user32.dll")]
    private static extern uint MapVirtualKey(uint code, uint mapType);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindow(string className, string windowName);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after,
                                              string className, string windowName);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern bool IsWindow(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hwnd, int command);

    [DllImport("user32.dll")]
    private static extern bool AttachThreadInput(uint attach, uint to, bool flag);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);

    [DllImport("user32.dll")]
    private static extern IntPtr GetKeyboardLayout(uint thread);

    [DllImport("user32.dll")]
    private static extern IntPtr SetFocus(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern bool PostMessage(IntPtr hwnd, uint message,
                                           IntPtr wparam, IntPtr lparam);

    public static IntPtr FindPad()
    {
        return FindWindow("LadoQaPadWindow", null);
    }

    public static IntPtr FindEdit(IntPtr parent)
    {
        return FindWindowEx(parent, IntPtr.Zero, "Edit", null);
    }

    public static bool Focus(IntPtr hwnd, IntPtr edit)
    {
        ShowWindow(hwnd, 9);
        uint foregroundPid;
        uint targetPid;
        uint foregroundThread = GetWindowThreadProcessId(GetForegroundWindow(), out foregroundPid);
        uint targetThread = GetWindowThreadProcessId(hwnd, out targetPid);
        bool attached = AttachThreadInput(foregroundThread, targetThread, true);
        bool ok = SetForegroundWindow(hwnd);
        SetFocus(edit);
        if (attached) AttachThreadInput(foregroundThread, targetThread, false);
        return ok;
    }

    public static int PrimaryLanguage(IntPtr hwnd)
    {
        uint pid;
        uint thread = GetWindowThreadProcessId(hwnd, out pid);
        long hkl = GetKeyboardLayout(thread).ToInt64();
        return (int)(hkl & 0x3FF);
    }

    public static void TypeKeys(ushort[] keys)
    {
        foreach (ushort key in keys)
        {
            SendVirtualKey(key, true);
            Thread.Sleep(18);
            SendVirtualKey(key, false);
            Thread.Sleep(18);
        }
    }

    public static void DoubleShift()
    {
        for (int i = 0; i < 2; i++)
        {
            SendVirtualKey(0xA0, true);
            Thread.Sleep(40);
            SendVirtualKey(0xA0, false);
            Thread.Sleep(50);
        }
    }

    public static void Dump(IntPtr pad)
    {
        PostMessage(pad, 0x8001, IntPtr.Zero, IntPtr.Zero);
    }

    public static IntPtr Foreground()
    {
        return GetForegroundWindow();
    }

    public static void RestoreForeground(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero || !IsWindow(hwnd)) return;
        uint pid;
        uint foregroundThread = GetWindowThreadProcessId(GetForegroundWindow(), out pid);
        uint targetThread = GetWindowThreadProcessId(hwnd, out pid);
        bool attached = false;
        if (foregroundThread != 0 && targetThread != 0 &&
            foregroundThread != targetThread)
        {
            attached = AttachThreadInput(foregroundThread, targetThread, true);
        }
        SetForegroundWindow(hwnd);
        if (attached) AttachThreadInput(foregroundThread, targetThread, false);
    }

    public static void Close(IntPtr hwnd)
    {
        PostMessage(hwnd, 0x0010, IntPtr.Zero, IntPtr.Zero);
    }

    private static void SendVirtualKey(ushort key, bool down)
    {
        INPUT input = new INPUT();
        input.type = 1;
        input.u.ki.wVk = key;
        input.u.ki.wScan = (ushort)MapVirtualKey(key, 0);
        input.u.ki.dwFlags = down ? 0u : 2u;
        input.u.ki.time = 0;
        input.u.ki.dwExtraInfo = IntPtr.Zero;
        INPUT[] batch = new INPUT[] { input };
        if (SendInput(1, batch, Marshal.SizeOf(typeof(INPUT))) != 1)
        {
            throw new InvalidOperationException("SendInput failed");
        }
    }
}
'@

$script:failures = 0
function Fail([string]$message) {
    Write-Host "FAIL: $message" -ForegroundColor Red
    $script:failures++
}

function Read-Report([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return '<no report>' }
    $text = Get-Content -LiteralPath $path -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($null -eq $text) { return '' }
    return [string]$text
}

function Wait-ForPad {
    $pad = [IntPtr]::Zero
    for ($i = 0; $i -lt 50 -and $pad -eq [IntPtr]::Zero; $i++) {
        Start-Sleep -Milliseconds 100
        $pad = [Qa]::FindPad()
    }
    if ($pad -eq [IntPtr]::Zero) { throw 'QA pad window did not appear' }
    return $pad
}

function Invoke-Scenario {
    param(
        [string]$Label,
        [string]$Arguments,
        [bool]$ExpectCorrection,
        [string]$ReportPath
    )

    Remove-Item -LiteralPath $ReportPath -ErrorAction SilentlyContinue
    $startArguments = "$Arguments --report `"$ReportPath`""
    Start-Process -FilePath $PadPath -ArgumentList $startArguments | Out-Null

    $pad = Wait-ForPad
    $edit = [Qa]::FindEdit($pad)
    if ($edit -eq [IntPtr]::Zero) { throw 'QA pad edit control not found' }

    [Qa]::Focus($pad, $edit) | Out-Null
    Start-Sleep -Milliseconds 800

    $language = [Qa]::PrimaryLanguage($pad)
    if ($language -eq 0x09) {
        # English layout: physical g-h-b-d-t-n spells "ghbdtn".
        $keys = [uint16[]](0x47, 0x48, 0x42, 0x44, 0x54, 0x4E, 0x20)
        $typed = 'ghbdtn '
        $corrected = 'привет '
    } elseif ($language -eq 0x19) {
        # Russian layout: physical h-e-l-l-o spells "руддщ".
        $keys = [uint16[]](0x48, 0x45, 0x4C, 0x4C, 0x4F, 0x20)
        $typed = 'руддщ '
        $corrected = 'hello '
    } else {
        throw ("unexpected input layout 0x{0:x2}; enable English or Russian" -f $language)
    }

    Write-Host "[$Label] layout=0x$($language.ToString('x2')), typing '$typed'"
    [Qa]::TypeKeys($keys)
    Start-Sleep -Milliseconds 500
    [Qa]::Dump($pad)
    Start-Sleep -Milliseconds 200
    $actual = Read-Report $ReportPath
    $wanted = if ($ExpectCorrection) { $corrected } else { $typed }
    if ($actual -ceq $wanted) {
        Write-Host "PASS [$Label] after Space: '$actual'"
    } else {
        Fail "[$Label] after Space: expected '$wanted', got '$actual'"
    }

    [Qa]::DoubleShift()
    Start-Sleep -Milliseconds 500
    [Qa]::Dump($pad)
    Start-Sleep -Milliseconds 200
    $reverted = Read-Report $ReportPath
    if ($reverted -ceq $typed) {
        Write-Host "PASS [$Label] after double Shift: '$reverted'"
    } else {
        Fail "[$Label] after double Shift: expected '$typed', got '$reverted'"
    }

    [Qa]::Close($pad) | Out-Null
    Start-Sleep -Milliseconds 400
}

Write-Host 'Stopping any running Lado...'
$previousForeground = [Qa]::Foreground()
Get-Process -Name Lado -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400

$textReport = Join-Path $env:TEMP 'lado-qa-text.txt'
$passwordReport = Join-Path $env:TEMP 'lado-qa-password.txt'

$env:LADO_QA_ACCEPT_INJECTED = '1'
try {
    Write-Host "Starting $LadoPath"
    Start-Process -FilePath $LadoPath | Out-Null
    Start-Sleep -Milliseconds 800

    Invoke-Scenario -Label 'text field' -Arguments '' -ExpectCorrection $true -ReportPath $textReport
    Invoke-Scenario -Label 'password field' -Arguments '--password' -ExpectCorrection $false -ReportPath $passwordReport
} finally {
    Remove-Item Env:\LADO_QA_ACCEPT_INJECTED -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
    Get-Process -Name Lado -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process -Name LadoQaPad -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Milliseconds 300
    [Qa]::RestoreForeground($previousForeground)
}

if ($script:failures -gt 0) { exit 1 }
Write-Host 'PASS: 4 end-to-end checks'
exit 0
