# duo.ps1 — launcher for the Claude + Codex duo CLI
# Works whether duo is pip-installed or run from a source checkout.
#
# Usage:
#   .\duo.ps1 "build a todo cli in ./scratch with tests"
#   .\duo.ps1 -Interactive "start with a plan for X"
#   .\duo.ps1 -Cwd "C:\work\repo" -MaxSteps 40 "goal here"

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]] $Prompt,

    [string] $Cwd = $PWD.ProviderPath,
    [int]    $MaxSteps = 30,
    [switch] $Interactive
)

$ErrorActionPreference = "Stop"

$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$goal = if ($Prompt) { ($Prompt -join " ") } else { "" }
$argv = @("--cwd", $Cwd, "--max-steps", $MaxSteps)
if ($Interactive) { $argv += "--interactive" }
if ($goal)        { $argv += $goal }

# 1) Prefer the installed `duo` entry point.
if (Get-Command duo -ErrorAction SilentlyContinue) {
    & duo @argv
    exit $LASTEXITCODE
}

# 2) Fallback: run from source via `python -m duo` with src/ on PYTHONPATH.
$srcDir = Join-Path $PSScriptRoot "src"
if (-not (Test-Path (Join-Path $srcDir "duo\__init__.py"))) {
    Write-Error "duo is not installed and source layout at $srcDir is missing. Run: pip install -e `"$PSScriptRoot`""
    exit 1
}

$pyCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue)       { $pyCmd = @("py", "-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pyCmd = @("python") }
else {
    Write-Error "No Python found on PATH (need `py -3` or `python`)."
    exit 1
}

$env:PYTHONPATH = if ($env:PYTHONPATH) { "$srcDir;$env:PYTHONPATH" } else { $srcDir }
& $pyCmd[0] @($pyCmd[1..($pyCmd.Length-1)] + @("-m", "duo") + $argv)
exit $LASTEXITCODE
