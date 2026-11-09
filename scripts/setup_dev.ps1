param(
    [string]$EnvironmentPath = '.venv-dev',
    [switch]$RunTests
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
if (Test-Path -LiteralPath $EnvironmentPath) {
    throw "Environment already exists at $EnvironmentPath. Choose a new path; existing environments are never replaced."
}
$evidenceDir = Join-Path $projectRoot ('outputs/local_setup/environment-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $evidenceDir | Out-Null
Start-Transcript -Path (Join-Path $evidenceDir 'setup.log') | Out-Null
try {
    & py -3.12 -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 environment creation failed.' }
    $python = Join-Path (Resolve-Path $EnvironmentPath).Path 'Scripts/python.exe'
    & $python -m pip install --disable-pip-version-check -r requirements-dev.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed; environment retained for diagnosis.' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency failed.' }
    & $python -B -m scripts.verify_environment --require-venv
    if ($LASTEXITCODE -ne 0) { throw 'Installed packages differ from the tested lock.' }
    if ($RunTests) {
        $env:MPLBACKEND = 'Agg'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        $testTemp = Join-Path ([IO.Path]::GetTempPath()) ('p2-' + [guid]::NewGuid().ToString('N'))
        & $python -B -m pytest tests -q "--basetemp=$testTemp" "--junitxml=$evidenceDir/pytest.xml" -o "cache_dir=$evidenceDir/pytest-cache"
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed; see the saved JUnit report.' }
    }
    Write-Output "Environment ready. Interpreter: $python. Evidence: $evidenceDir"
}
finally {
    Stop-Transcript | Out-Null
}
