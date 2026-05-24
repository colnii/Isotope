"""Windows screen backend using local PowerShell and Win32 APIs."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .screen_backend_types import (
    ScreenBackendOutputArtifact,
    ScreenBackendRequest,
    ScreenBackendResult,
)


class WindowsScreenBackend:
    """Best-effort Windows backend for screen observe/control requests."""

    def __init__(
        self,
        *,
        powershell_path: str = "powershell.exe",
        timeout_seconds: int = 5,
    ) -> None:
        self.powershell_path = powershell_path
        self.timeout_seconds = timeout_seconds

    def run(self, request: ScreenBackendRequest) -> ScreenBackendResult:
        if not isinstance(request, ScreenBackendRequest):
            raise TypeError("WindowsScreenBackend.run requires a ScreenBackendRequest")
        started_at = _now()
        if sys.platform != "win32":
            return _failed_result(
                started_at=started_at,
                summary="Windows screen backend is unavailable on this platform",
                reason_code="screen_windows_backend_unavailable",
                retryable=False,
            )

        try:
            return self._run_powershell(request=request, started_at=started_at)
        except FileNotFoundError:
            return _failed_result(
                started_at=started_at,
                summary="powershell.exe is not available",
                reason_code="screen_windows_backend_unavailable",
                retryable=False,
            )
        except subprocess.TimeoutExpired as exc:
            return _failed_result(
                started_at=started_at,
                summary="Windows screen backend timed out",
                reason_code="screen_windows_backend_timeout",
                retryable=True,
                diagnostic=str(exc),
            )

    def _run_powershell(
        self,
        *,
        request: ScreenBackendRequest,
        started_at: str,
    ) -> ScreenBackendResult:
        with tempfile.TemporaryDirectory(prefix="isotope-screen-") as temp_root:
            root = Path(temp_root)
            request_path = root / "request.json"
            output_path = root / "result.json"
            script_path = root / "screen_backend.ps1"
            request_path.write_text(
                json.dumps(_request_payload(request), sort_keys=True),
                encoding="utf-8",
            )
            script_path.write_text(_POWERSHELL_SCRIPT, encoding="utf-8")
            completed = subprocess.run(
                [
                    self.powershell_path,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    str(request_path),
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                return _failed_result(
                    started_at=started_at,
                    summary="Windows screen backend failed",
                    reason_code="screen_windows_backend_failed",
                    retryable=False,
                    diagnostic=completed.stdout + completed.stderr,
                )
            try:
                raw_result = json.loads(output_path.read_text(encoding="utf-8"))
            except Exception as exc:
                return _failed_result(
                    started_at=started_at,
                    summary="Windows screen backend returned malformed output",
                    reason_code="screen_windows_backend_protocol_error",
                    retryable=False,
                    diagnostic=f"{exc}\n{completed.stdout}\n{completed.stderr}",
                )
            return _result_from_payload(raw_result, started_at=started_at)


def _request_payload(request: ScreenBackendRequest) -> dict[str, Any]:
    return {
        "operation": request.operation,
        "tool_name": request.tool_name,
        "target_selector": {
            "kind": request.target_selector.kind,
            "selector": dict(request.target_selector.selector),
        },
        "mode": request.mode,
        "capture": list(request.capture),
        "execution_mode": request.execution_mode,
        "actions": [action.to_dict() for action in request.actions],
        "artifact_policy": dict(request.artifact_policy),
        "budget": dict(request.budget),
    }


def _result_from_payload(payload: dict[str, Any], *, started_at: str) -> ScreenBackendResult:
    output_artifacts = [
        ScreenBackendOutputArtifact(
            artifact_type=str(item["artifact_type"]),
            summary=str(item["summary"]),
            content=str(item["content"]),
        )
        for item in payload.get("output_artifacts", [])
        if isinstance(item, dict)
    ]
    return ScreenBackendResult(
        backend_session_id=str(payload.get("backend_session_id", "windows_screen_session")),
        status=str(payload.get("status", "failed")),
        started_at=str(payload.get("started_at", started_at)),
        finished_at=str(payload.get("finished_at", _now())),
        summary=str(payload.get("summary", "Windows screen backend completed")),
        output_artifacts=output_artifacts,
        reason_code=str(payload.get("reason_code", "screen_windows_backend_completed")),
        retryable=payload.get("retryable") is True,
        resource_usage=dict(payload.get("resource_usage", {})),
    )


def _failed_result(
    *,
    started_at: str,
    summary: str,
    reason_code: str,
    retryable: bool,
    diagnostic: str | None = None,
) -> ScreenBackendResult:
    output_artifacts: list[ScreenBackendOutputArtifact] = []
    if diagnostic:
        output_artifacts.append(
            ScreenBackendOutputArtifact(
                artifact_type="screen_diagnostic",
                summary="Windows screen backend diagnostic",
                content=diagnostic,
            )
        )
    return ScreenBackendResult(
        backend_session_id="windows_screen_unavailable",
        status="failed",
        started_at=started_at,
        finished_at=_now(),
        summary=summary,
        output_artifacts=output_artifacts,
        reason_code=reason_code,
        retryable=retryable,
        resource_usage={},
    )


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_POWERSHELL_SCRIPT = textwrap.dedent(
    r'''
    param(
        [Parameter(Mandatory=$true)][string]$RequestPath,
        [Parameter(Mandatory=$true)][string]$OutputPath
    )

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type @"
    using System;
    using System.Text;
    using System.Runtime.InteropServices;
    public class NativeScreen {
        public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
        [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
        [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
        [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
        [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
        [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
        [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    }
"@

    $MouseMove = 0x0001
    $LeftDown = 0x0002
    $LeftUp = 0x0004
    $RightDown = 0x0008
    $RightUp = 0x0010
    $MiddleDown = 0x0020
    $MiddleUp = 0x0040
    $Wheel = 0x0800

    function NowIso { return [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") }

    function Read-Request {
        return Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
    }

    function Get-Windows {
        $items = New-Object System.Collections.Generic.List[object]
        [NativeScreen]::EnumWindows({
            param([IntPtr]$hWnd, [IntPtr]$lParam)
            if (-not [NativeScreen]::IsWindowVisible($hWnd)) { return $true }
            $builder = New-Object System.Text.StringBuilder 512
            [void][NativeScreen]::GetWindowText($hWnd, $builder, $builder.Capacity)
            $title = $builder.ToString()
            if ([string]::IsNullOrWhiteSpace($title)) { return $true }
            $pid = 0
            [void][NativeScreen]::GetWindowThreadProcessId($hWnd, [ref]$pid)
            $processName = ""
            try { $processName = (Get-Process -Id $pid -ErrorAction Stop).ProcessName + ".exe" } catch {}
            $rect = New-Object NativeScreen+RECT
            [void][NativeScreen]::GetWindowRect($hWnd, [ref]$rect)
            $items.Add([pscustomobject]@{
                window_id = $hWnd.ToInt64().ToString()
                title = $title
                process = $processName
                bounds = @{
                    left = $rect.Left
                    top = $rect.Top
                    width = [Math]::Max(0, $rect.Right - $rect.Left)
                    height = [Math]::Max(0, $rect.Bottom - $rect.Top)
                }
            })
            return $true
        }, [IntPtr]::Zero) | Out-Null
        return $items
    }

    function Select-Target($windows, $selector) {
        foreach ($window in $windows) {
            $matches = $true
            if ($selector.app -and ($window.process -ine $selector.app)) { $matches = $false }
            if ($selector.title_contains -and ($window.title -notlike ("*" + $selector.title_contains + "*"))) { $matches = $false }
            if ($selector.window_id -and ($window.window_id -ne $selector.window_id)) { $matches = $false }
            if ($matches) { return $window }
        }
        return $null
    }

    function Add-Artifact($artifacts, [string]$type, [string]$summary, [string]$content) {
        $artifacts.Add([pscustomobject]@{
            artifact_type = $type
            summary = $summary
            content = $content
        })
    }

    function Capture-Screenshot($target, $policy) {
        $bounds = $target.bounds
        if (-not $bounds -or $bounds.width -le 0 -or $bounds.height -le 0) { throw "target bounds are not capturable" }
        $maxWidth = [int]$policy.max_screenshot_width
        $maxHeight = [int]$policy.max_screenshot_height
        $width = [Math]::Min([int]$bounds.width, $maxWidth)
        $height = [Math]::Min([int]$bounds.height, $maxHeight)
        $bitmap = New-Object System.Drawing.Bitmap $width, $height
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $stream = New-Object System.IO.MemoryStream
        try {
            $graphics.CopyFromScreen([int]$bounds.left, [int]$bounds.top, 0, 0, $bitmap.Size)
            $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
            $bytes = $stream.ToArray()
            if ($bytes.Length -gt [int]$policy.max_screenshot_bytes) { throw "screenshot exceeds byte cap" }
            return @{
                encoding = "base64"
                media_type = "image/png"
                scaled = (($width -ne [int]$bounds.width) -or ($height -ne [int]$bounds.height))
                width = $width
                height = $height
                data = [Convert]::ToBase64String($bytes)
            } | ConvertTo-Json -Compress
        } finally {
            $graphics.Dispose()
            $bitmap.Dispose()
            $stream.Dispose()
        }
    }

    function Invoke-Control($target, $actions, [string]$executionMode) {
        $applied = 0
        if ($executionMode -ne "execute") { return @{ action_count = $actions.Count; executed = $false } }
        [void][NativeScreen]::SetForegroundWindow([IntPtr]::new([Int64]::Parse($target.window_id)))
        foreach ($action in $actions) {
            if ($null -ne $action.x -and $null -ne $action.y) {
                [void][NativeScreen]::SetCursorPos([int]$action.x, [int]$action.y)
            }
            if ($action.type -eq "move") { $applied += 1; continue }
            if ($action.type -eq "click") {
                $down = $LeftDown; $up = $LeftUp
                if ($action.button -eq "right") { $down = $RightDown; $up = $RightUp }
                if ($action.button -eq "middle") { $down = $MiddleDown; $up = $MiddleUp }
                [NativeScreen]::mouse_event($down, 0, 0, 0, [UIntPtr]::Zero)
                [NativeScreen]::mouse_event($up, 0, 0, 0, [UIntPtr]::Zero)
                $applied += 1
            } elseif ($action.type -eq "wheel") {
                [NativeScreen]::mouse_event($Wheel, 0, 0, [uint32]$action.delta_y, [UIntPtr]::Zero)
                $applied += 1
            } elseif ($action.type -eq "key_press" -and $action.key) {
                [System.Windows.Forms.SendKeys]::SendWait([string]$action.key)
                $applied += 1
            }
        }
        return @{ action_count = $actions.Count; executed = $true; applied_count = $applied }
    }

    $started = NowIso
    $artifacts = New-Object System.Collections.Generic.List[object]
    try {
        $request = Read-Request
        $windows = Get-Windows
        $selector = $request.target_selector.selector
        $target = Select-Target $windows $selector
        $metadata = @{
            window_count = $windows.Count
            target_found = ($null -ne $target)
            target = $target
        } | ConvertTo-Json -Depth 8 -Compress
        if ($request.capture -contains "metadata") {
            Add-Artifact $artifacts "screen_metadata" "screen metadata captured" $metadata
        }
        if ($null -eq $target) {
            $status = "not_observable"
            $summary = "screen target was not observable"
            $reason = "screen_target_not_observable"
        } elseif ($request.operation -eq "control") {
            $control = Invoke-Control $target $request.actions $request.execution_mode
            $artifactType = "screen_control_plan"
            if ($request.execution_mode -eq "execute") { $artifactType = "screen_control_result" }
            Add-Artifact $artifacts $artifactType "screen control result" ($control | ConvertTo-Json -Compress)
            $status = "completed"
            $summary = "screen control completed"
            $reason = "screen_control_completed"
        } else {
            if ($request.capture -contains "screenshot") {
                try {
                    Add-Artifact $artifacts "screen_screenshot" "screen screenshot captured" (Capture-Screenshot $target $request.artifact_policy)
                } catch {
                    Add-Artifact $artifacts "screen_diagnostic" "screen screenshot diagnostic" $_.Exception.Message
                }
            }
            $status = "captured"
            $summary = "screen observe captured"
            $reason = "screen_observe_captured"
        }
        @{
            backend_session_id = "windows_screen_" + [Guid]::NewGuid().ToString("N")
            status = $status
            started_at = $started
            finished_at = NowIso
            summary = $summary
            output_artifacts = $artifacts
            reason_code = $reason
            retryable = $false
            resource_usage = @{ window_count = $windows.Count }
        } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    } catch {
        Add-Artifact $artifacts "screen_diagnostic" "Windows screen backend diagnostic" $_.Exception.ToString()
        @{
            backend_session_id = "windows_screen_" + [Guid]::NewGuid().ToString("N")
            status = "failed"
            started_at = $started
            finished_at = NowIso
            summary = "Windows screen backend failed"
            output_artifacts = $artifacts
            reason_code = "screen_windows_backend_failed"
            retryable = $false
            resource_usage = @{}
        } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    '''
)


__all__ = ["WindowsScreenBackend"]
