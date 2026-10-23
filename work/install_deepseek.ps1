<# Install the official CLI and keep its state and caches beside it on D:. #>
param(
    [string]$InstallRoot = 'D:\AI\DeepSeek',
    [string]$Version = '0.2.1-rc.2',
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$dsRoot = [IO.Path]::GetFullPath($InstallRoot)
if ([IO.Path]::GetPathRoot($dsRoot) -eq 'C:\') { throw 'Choose an installation directory outside C:.' }
$dsNode = (Get-Command node.exe -ErrorAction Stop).Source
$dsNpm = (Get-Command npm.cmd -ErrorAction Stop).Source
$dsNodeVersion = [version]((& $dsNode --version).TrimStart('v'))
if (($dsNodeVersion.Major -eq 22 -and $dsNodeVersion.Minor -lt 19) -or $dsNodeVersion.Major -lt 22 -or $dsNodeVersion.Major -eq 23) { throw 'DeepSeek Harness requires Node.js 22.19+ or 24+.' }
foreach ($folder in @('cli','bin','data','cache\npm','cache\pnpm','cache\pnpm-store','cache\corepack','tmp','workspace\files','workspace\.runtime-temp','logs')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $dsRoot $folder) | Out-Null
}
$env:DSH_HOME = Join-Path $dsRoot 'data'
$env:TEMP = Join-Path $dsRoot 'tmp'
$env:TMP = $env:TEMP
$env:npm_config_cache = Join-Path $dsRoot 'cache\npm'
$env:npm_config_store_dir = Join-Path $dsRoot 'cache\pnpm-store'
$env:PNPM_HOME = Join-Path $dsRoot 'cache\pnpm'
$env:COREPACK_HOME = Join-Path $dsRoot 'cache\corepack'
$env:XDG_CACHE_HOME = Join-Path $dsRoot 'cache'
$env:DSH_TELEMETRY_DISABLED = '1'
$env:DSH_PERMISSION_MODE = 'workspace-write'
if (-not $SkipInstall) {
    & $dsNpm install --global --prefix (Join-Path $dsRoot 'cli') --cache $env:npm_config_cache "@deepseek-ai/dsh@$Version"
    if ($LASTEXITCODE -ne 0) { throw 'DeepSeek npm installation failed.' }
}
$dsCli = Join-Path $dsRoot 'cli\dsh.cmd'
if (-not (Test-Path -LiteralPath $dsCli)) { throw 'The CLI is missing. Run without -SkipInstall.' }
$dsActualVersion = (& $dsCli --version).Trim()
if ($LASTEXITCODE -ne 0) { throw 'The installed CLI failed its version check.' }
# Keep this separate from profile settings, which the official Models page edits.
# A pre-existing configuration is always preserved on subsequent setup runs.
$dsPatch = Join-Path $dsRoot 'data\cordis.patch.yml'
if (-not (Test-Path -LiteralPath $dsPatch)) {
    @'
- id: llm-deepseek
  config:
    baseURL: https://api.deepseek.com/anthropic
    apiKeyEnv: DEEPSEEK_API_KEY
    thinking: disabled
    reasoningEffort: off
    maxTokens: 4096
    defaultContextWindow: 65536
    models:
      - id: deepseek-flash
        name: DeepSeek Flash
        contextWindow: 65536
        maxTokens: 4096
        inputModalities: [text, image]
- id: agent-default-model
  config:
    provider: deepseek-official
    model: deepseek-flash
'@ | Set-Content -LiteralPath $dsPatch -Encoding utf8
}
@{node=$dsNode; version=$dsActualVersion} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dsRoot 'runtime.json') -Encoding utf8
$dsWrapper = @"
@echo off
set "DSH_HOME=$dsRoot\data"
set "TEMP=$dsRoot\workspace\.runtime-temp"
set "TMP=$dsRoot\workspace\.runtime-temp"
set "npm_config_cache=$dsRoot\cache\npm"
set "npm_config_store_dir=$dsRoot\cache\pnpm-store"
set "PNPM_HOME=$dsRoot\cache\pnpm"
set "COREPACK_HOME=$dsRoot\cache\corepack"
set "XDG_CACHE_HOME=$dsRoot\cache"
set "DSH_TELEMETRY_DISABLED=1"
set "DSH_PERMISSION_MODE=workspace-write"
"$dsNode" "$dsRoot\cli\node_modules\@deepseek-ai\dsh\lib\bin.js" %*
"@
$dsWrapper | Set-Content -LiteralPath (Join-Path $dsRoot 'bin\dsh.cmd') -Encoding ascii
$dsPetExe = Join-Path (Split-Path -Parent $PSScriptRoot) 'CitlaliDesktopPet.exe'
@"
@echo off
chcp 65001 >nul
set "TEMP=$dsRoot\tmp"
set "TMP=$dsRoot\tmp"
set "CITLALI_DEEPSEEK_ROOT=$dsRoot"
start "" "$dsPetExe" --deepseek
"@ | ForEach-Object { [IO.File]::WriteAllText((Join-Path $dsRoot 'Open DeepSeek.cmd'), $_, [Text.UTF8Encoding]::new($false)) }
[Environment]::SetEnvironmentVariable('CITLALI_DEEPSEEK_ROOT', $dsRoot, 'User')
$dsUserPath = [string][Environment]::GetEnvironmentVariable('Path', 'User')
$dsBin = Join-Path $dsRoot 'bin'
if ($dsUserPath.Split(';') -notcontains $dsBin) {
    [Environment]::SetEnvironmentVariable('Path', ($dsUserPath.TrimEnd(';')+';'+$dsBin), 'User')
}
$env:CITLALI_DEEPSEEK_ROOT = $dsRoot
$env:Path = $dsBin+';'+$env:Path
Write-Output "Installed official DeepSeek Harness $dsActualVersion at $dsRoot"
Write-Output 'Model menu: deepseek-flash; default output: 4096 tokens; permission: workspace-write.'
Write-Output 'Enter your API key locally in the official Web UI: Settings > Models.'
