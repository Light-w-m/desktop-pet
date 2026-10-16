param(
    [switch]$Apply,
    [switch]$RecycleOlderBackups,
    [switch]$RecycleGenerated,
    [string]$KeepBackup
)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')

function Assert-WorkspacePath([string]$path) {
    $absolute = [IO.Path]::GetFullPath($path)
    if (-not $absolute.StartsWith($workspace + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing a path outside this workspace: $absolute"
    }
    $cursor = $absolute
    while ($cursor -and $cursor -ne $workspace) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing to traverse a junction or symbolic link: $cursor"
            }
        }
        $cursor = Split-Path -Parent $cursor
    }
    if (Test-Path -LiteralPath $absolute -PathType Container) {
        $pending = [Collections.Generic.Stack[string]]::new()
        $pending.Push($absolute)
        while ($pending.Count -gt 0) {
            foreach ($child in Get-ChildItem -LiteralPath $pending.Pop() -Directory -Force) {
                if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    throw "Refusing a nested directory link: $($child.FullName)"
                }
                $pending.Push($child.FullName)
            }
        }
    }
    return $absolute
}

function Get-Bytes([string]$path) {
    $item = Get-Item -LiteralPath $path -Force
    if ($item.PSIsContainer) {
        return [long](Get-ChildItem -LiteralPath $path -Recurse -File -Force |
            Measure-Object -Property Length -Sum).Sum
    }
    return [long]$item.Length
}

$plan = @()
foreach ($relative in @('work/pyinstaller-build', 'work/dist', 'work/github-publish-check',
    'work/git-publish-tmp', 'work/sources/compact-candidate', 'work/sources/drag-deps',
    '__pycache__', 'work/__pycache__')) {
    $path = Assert-WorkspacePath (Join-Path $workspace $relative)
    if (Test-Path -LiteralPath $path) {
        $plan += [pscustomobject]@{relative=$relative; path=$path; bytes=(Get-Bytes $path); mode='generated'}
    }
}
$manifest = Get-Content -LiteralPath (Join-Path $workspace 'assets/manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($animation in $manifest.animations.PSObject.Properties) {
    $name = $animation.Value.file
    $path = Assert-WorkspacePath (Join-Path $workspace ('work/repaired-assets/' + $name))
    $original = Assert-WorkspacePath (Join-Path $workspace ('assets/' + $name))
    if ((Test-Path -LiteralPath $path) -and
        (Get-FileHash -LiteralPath $path).Hash -eq (Get-FileHash -LiteralPath $original).Hash) {
        $plan += [pscustomobject]@{relative=('work/repaired-assets/' + $name); path=$path; bytes=(Get-Bytes $path); mode='duplicate'}
    }
}
# Video decoding is reproducible; keep the exact four imagegen source frames
# and all guides/prompts while allowing the remaining diagnostics to be recycled.
$videoCache = Assert-WorkspacePath (Join-Path $workspace 'local-media/stomp-video')
if (Test-Path -LiteralPath $videoCache -PathType Container) {
    $retainedFrames = @('frame-001.png', 'frame-033.png', 'frame-082.png', 'frame-136.png')
    foreach ($item in Get-ChildItem -LiteralPath $videoCache -File) {
        if ($item.Name -match '^(frame|matte|stabilized)-[0-9]+\.png$' -and $item.Name -notin $retainedFrames) {
            $checked = Assert-WorkspacePath $item.FullName
            $plan += [pscustomobject]@{relative=('local-media/stomp-video/' + $item.Name); path=$checked; bytes=$item.Length; mode='generated'}
        }
    }
}
if ($RecycleOlderBackups) {
    if (-not $KeepBackup) { throw 'Specify the most recent backup directory to preserve.' }
    $preserved = Assert-WorkspacePath (Join-Path $workspace $KeepBackup)
    $backupRoot = Join-Path $workspace 'backups'
    if (-not (Test-Path -LiteralPath $preserved -PathType Container) -or
        (Split-Path -Parent $preserved) -ne $backupRoot) {
        throw 'The preserved snapshot must be an existing direct child of backups.'
    }
    foreach ($item in Get-ChildItem -LiteralPath $backupRoot -Force) {
        if ($item.FullName -eq $preserved) { continue }
        $path = Assert-WorkspacePath $item.FullName
        $plan += [pscustomobject]@{relative=('backups/' + $item.Name); path=$path; bytes=(Get-Bytes $path); mode='recycle'}
    }
}

if ($RecycleGenerated) {
    foreach ($entry in $plan) {
        if ($entry.mode -in @('generated', 'duplicate')) { $entry.mode = 'recycle' }
    }
}

foreach ($entry in $plan) {
    Write-Output ('{0}: {1:N1} MiB - {2}' -f $entry.mode, ($entry.bytes / 1MB), $entry.relative)
}
if (-not $Apply) { Write-Output 'Preview only; use -Apply to execute this plan.'; exit }

Add-Type -AssemblyName Microsoft.VisualBasic
foreach ($entry in $plan) {
    $checked = Assert-WorkspacePath $entry.path
    if ($entry.mode -eq 'recycle') {
        if (Test-Path -LiteralPath $checked -PathType Container) {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($checked,
                [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)
        } else {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($checked,
                [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)
        }
    } else {
        Remove-Item -LiteralPath $checked -Recurse -Force
    }
}
$report = [pscustomobject]@{
    preserved_backup=$KeepBackup
    recycled_bytes=[long](($plan | Where-Object mode -eq 'recycle' | Measure-Object bytes -Sum).Sum)
    generated_bytes_removed=[long](($plan | Where-Object mode -ne 'recycle' | Measure-Object bytes -Sum).Sum)
    entries=@($plan | Group-Object { if ($_.relative -like 'local-media/stomp-video/*') {
            'local-media/stomp-video (generated frames only)'
        } else { $_.relative } } | ForEach-Object {
            [pscustomobject]@{relative=$_.Name; bytes=[long](($_.Group | Measure-Object bytes -Sum).Sum);
                paths=$_.Count; mode=$_.Group[0].mode}
        })
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $workspace 'work/storage-cleanup.json') -Encoding UTF8
