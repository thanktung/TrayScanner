# fix_torch_dll.ps1
# Run this AFTER any `pip install torch` / `pip install --upgrade torch` / recreating
# the venv — torch==2.8.0 still needs a newer msvcp140.dll family than what Windows
# ships by default on this machine, and the company blocks installing VC++
# Redistributable (both normal install and /layout extraction -> Access Denied).
# This script borrows the newer DLLs from already-installed apps (OneDrive, Copilot)
# and copies them locally into torch\lib — no admin rights needed, does not touch
# System32.
#
# Usage:
#   cd D:\Travis\H08_TrayScanner
#   .\scripts\fix_torch_dll.ps1

$ErrorActionPreference = "Stop"

$libdir = Join-Path $PSScriptRoot "..\.venv\Lib\site-packages\torch\lib" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $libdir) {
    Write-Error "Khong tim thay .venv\Lib\site-packages\torch\lib — da cai torch chua? (pip install torch==2.8.0 torchvision==0.23.0)"
    exit 1
}

$oneDrive = "C:\Program Files\Microsoft OneDrive"
$oneDriveVer = Get-ChildItem $oneDrive -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d+\.\d+' } | Sort-Object { [version]($_.Name -replace '[^\d.]','') } -Descending | Select-Object -First 1
$copilot = Get-ChildItem "C:\Program Files (x86)\Microsoft\Copilot\Application" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^\d' } | Sort-Object Name -Descending | Select-Object -First 1

if (-not $oneDriveVer) { Write-Error "Khong tim thay OneDrive install — can nguon DLL khac."; exit 1 }

$fromOneDrive = @("msvcp140.dll","msvcp140_1.dll","vcruntime140.dll","vcruntime140_1.dll","concrt140.dll")
foreach ($f in $fromOneDrive) {
    $src = Join-Path $oneDriveVer.FullName $f
    if (Test-Path $src) {
        Copy-Item $src -Destination $libdir -Force
        Write-Output "copied (OneDrive): $f"
    } else {
        Write-Warning "khong tim thay trong OneDrive: $f"
    }
}

if ($copilot) {
    $fromCopilot = @("msvcp140_codecvt_ids.dll","vccorlib140.dll")
    foreach ($f in $fromCopilot) {
        $src = Join-Path $copilot.FullName $f
        if (Test-Path $src) {
            Copy-Item $src -Destination $libdir -Force
            Write-Output "copied (Copilot): $f"
        } else {
            Write-Warning "khong tim thay trong Copilot: $f"
        }
    }
} else {
    Write-Warning "Khong tim thay Copilot install — bo qua msvcp140_codecvt_ids.dll / vccorlib140.dll (co the khong can neu da co san)."
}

Write-Output ""
Write-Output "Xong. Test lai bang:"
Write-Output "  .venv\Scripts\python.exe -c `"import torch; print('torch OK', torch.__version__)`""

