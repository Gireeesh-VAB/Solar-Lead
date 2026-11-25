# Starts the obstacle service on http://127.0.0.1:8200 (Ctrl+C to stop).
# Python: OBSTACLE_PYTHON if set, else .venv\Scripts\python.exe in this folder, else the solar-fitness backend's environment (it already has every package).
# Maps key: the environment or this folder's .env first. If neither has GOOGLE_MAPS_API_KEY, it is borrowed from the solar-fitness backend's .env
# for THIS PROCESS ONLY - nothing is copied to disk and the value is never printed.
$here = $PSScriptRoot
# @(...) around the pipeline: with a single match PowerShell returns a plain string, and $candidates[0] would be its first letter.
$candidates = @(@($env:OBSTACLE_PYTHON, (Join-Path $here '.venv\Scripts\python.exe'), (Join-Path $here '..\solar-fitness\backend\.venv\Scripts\python.exe')) | Where-Object { $_ -and (Test-Path $_) })
if ($candidates.Count -eq 0) { Write-Error 'No Python found. Create a venv here and run: pip install -r requirements.txt'; exit 1 }

$ownEnv = Join-Path $here '.env'
$hasKey = [bool]$env:GOOGLE_MAPS_API_KEY -or ((Test-Path $ownEnv) -and (Select-String -Path $ownEnv -Pattern '^\s*GOOGLE_MAPS_API_KEY\s*=\s*\S' -Quiet))
if (-not $hasKey) {
    $appEnv = Join-Path $here '..\solar-fitness\backend\.env'
    if (Test-Path $appEnv) {
        $m = Select-String -Path $appEnv -Pattern '^\s*GOOGLE_MAPS_API_KEY\s*=\s*(\S+)' | Select-Object -First 1
        if ($m) {
            $env:GOOGLE_MAPS_API_KEY = $m.Matches[0].Groups[1].Value.Trim('"', "'")
            Write-Host 'GOOGLE_MAPS_API_KEY: borrowed from the solar-fitness backend .env (this process only)'
        }
    }
}
if (-not $env:GOOGLE_MAPS_API_KEY -and -not $hasKey) { Write-Warning 'No GOOGLE_MAPS_API_KEY found: /detect will answer 502 until one is set (.env.example).' }

Set-Location $here
& $candidates[0] -m uvicorn app:app --host 127.0.0.1 --port 8200
