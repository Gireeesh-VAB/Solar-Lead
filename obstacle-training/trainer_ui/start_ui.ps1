# Starts the trainer page on http://127.0.0.1:8766 (Ctrl+C to stop).
# Python: OBSTACLE_PYTHON if set, else .venv in obstacle-service / obstacle-training, else the solar-fitness backend's environment (it has every package).
$root = Split-Path -Parent $PSScriptRoot
$top = Split-Path -Parent $root
$candidates = @(@($env:OBSTACLE_PYTHON,
        (Join-Path $root '.venv\Scripts\python.exe'),
        (Join-Path $top 'obstacle-service\.venv\Scripts\python.exe'),
        (Join-Path $top 'solar-fitness\backend\.venv\Scripts\python.exe')) | Where-Object { $_ -and (Test-Path $_) })
if ($candidates.Count -eq 0) { Write-Error 'No Python found (set OBSTACLE_PYTHON).'; exit 1 }
Set-Location $PSScriptRoot
& $candidates[0] server.py
