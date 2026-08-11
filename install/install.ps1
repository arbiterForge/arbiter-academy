[CmdletBinding()]
param(
    [Parameter()]
    [string]$BundlePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Release = "preview-0.5"
$ArchiveName = "arbiter-academy-preview-0.5.zip"
$BundleSha256 = "e80bd3fa6004670f3b26e68dfa001aae3d41ba0e197a9ae92aafe3d597044bb3"
$AssetUrl = "https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.5/arbiter-academy-preview-0.5.zip"

function Assert-PathInside {
    param([string]$Root, [string]$Candidate)
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $candidateFull = [IO.Path]::GetFullPath($Candidate)
    if (-not $candidateFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "installer path escapes the user-owned Academy directory"
    }
}

function Test-PlainDirectory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    $item = Get-Item -LiteralPath $Path -Force
    return -not [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function New-OwnershipToken {
    $bytes = New-Object byte[] 32
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($bytes) } finally { $random.Dispose() }
    return [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
}

function Write-OwnershipMarker {
    param([string]$Path, [string]$Token)
    $payload = [Text.Encoding]::ASCII.GetBytes($Token + "`n")
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($payload, 0, $payload.Length) } finally { $stream.Dispose() }
}

function Test-OwnedDirectory {
    param([string]$AcademyRoot, [string]$Directory, [string]$Marker, [string]$Token)
    try {
        Assert-PathInside -Root $AcademyRoot -Candidate $Directory
        if (-not (Test-PlainDirectory $AcademyRoot) -or -not (Test-PlainDirectory $Directory)) { return $false }
        if (-not (Test-Path -LiteralPath $Marker -PathType Leaf)) { return $false }
        $markerItem = Get-Item -LiteralPath $Marker -Force
        if ($markerItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $false }
        return [IO.File]::ReadAllText($Marker, [Text.Encoding]::ASCII) -ceq ($Token + "`n")
    } catch {
        return $false
    }
}

function Remove-OwnedDirectory {
    param(
        [string]$AcademyRoot,
        [string]$Directory,
        [string]$Marker,
        [string]$Token,
        [string]$Label
    )
    if (-not (Test-OwnedDirectory -AcademyRoot $AcademyRoot -Directory $Directory -Marker $Marker -Token $Token)) {
        [Console]::Error.WriteLine("rollback ownership check failed for $Label; preserving it")
        return
    }
    $quarantine = Join-Path $AcademyRoot (".academy-delete-" + [Guid]::NewGuid().ToString("N"))
    Assert-PathInside -Root $AcademyRoot -Candidate $quarantine
    Move-Item -LiteralPath $Directory -Destination $quarantine -ErrorAction Stop
    $quarantineMarker = Join-Path $quarantine ([IO.Path]::GetFileName($Marker))
    if (-not (Test-OwnedDirectory -AcademyRoot $AcademyRoot -Directory $quarantine -Marker $quarantineMarker -Token $Token)) {
        [Console]::Error.WriteLine("rollback ownership check failed after quarantining $Label; preserving it")
        return
    }
    Remove-Item -LiteralPath $quarantine -Recurse -Force
}

function Test-TrustedReleaseRedirect {
    param([Uri]$Current, [Uri]$Next)
    $trustedFirstHop = $Current.Host -eq "github.com" -and $Next.Host -eq "release-assets.githubusercontent.com"
    $trustedCdnHop = $Current.Host -eq "release-assets.githubusercontent.com" -and $Next.Host -eq "release-assets.githubusercontent.com"
    return (
        $Next.Scheme -eq "https" -and
        $Next.IsDefaultPort -and
        -not $Next.UserInfo -and
        -not $Next.Fragment -and
        ($trustedFirstHop -or $trustedCdnHop)
    )
}

function Get-ImmutableReleaseAsset {
    param([string]$Url, [string]$Destination)
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $client = New-Object Net.Http.HttpClient($handler)
    try {
        $current = [Uri]$Url
        for ($redirects = 0; $redirects -le 3; $redirects++) {
            $response = $client.GetAsync($current, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            try {
                $status = [int]$response.StatusCode
                if ($status -ge 300 -and $status -lt 400) {
                    if ($redirects -eq 3 -or $null -eq $response.Headers.Location) {
                        throw "release asset redirect chain is missing or too long"
                    }
                    $next = if ($response.Headers.Location.IsAbsoluteUri) {
                        $response.Headers.Location
                    } else {
                        New-Object Uri($current, $response.Headers.Location)
                    }
                    if (-not (Test-TrustedReleaseRedirect $current $next)) {
                        throw "release asset redirected to an untrusted or mutable location"
                    }
                    $current = $next
                    continue
                }
                if ($status -ne 200) {
                    throw "release asset download returned HTTP $status"
                }
                if ($current.Host -ne "github.com" -and $current.Host -ne "release-assets.githubusercontent.com") {
                    throw "release asset response came from an untrusted host"
                }
                $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
                try {
                    $file = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                    try { $stream.CopyTo($file) } finally { $file.Dispose() }
                } finally { $stream.Dispose() }
                return
            } finally { $response.Dispose() }
        }
        throw "release asset redirect chain did not terminate"
    } finally {
        $client.Dispose()
        $handler.Dispose()
    }
}

function Expand-ReviewedBundle {
    param([string]$Archive, [string]$Destination)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $destinationFull = [IO.Path]::GetFullPath($Destination).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $names = @($zip.Entries | ForEach-Object { $_.FullName })
        $uniqueNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($name in $names) {
            if (-not $uniqueNames.Add($name)) {
                throw "bundle contains duplicate or case-colliding paths"
            }
        }
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName.Contains("\") -or $entry.FullName.StartsWith("/") -or $entry.FullName.Contains(":")) {
                throw "bundle contains an unsafe archive path"
            }
            $segments = $entry.FullName.Split("/")
            if ($segments -contains ".." -or $segments -contains "." -or $segments -contains "") {
                throw "bundle contains an unsafe archive path"
            }
            $unixType = (($entry.ExternalAttributes -shr 16) -band 0xF000)
            if ($unixType -eq 0xA000) {
                throw "bundle contains a symbolic link"
            }
            $target = [IO.Path]::GetFullPath((Join-Path $Destination $entry.FullName))
            if (-not $target.StartsWith($destinationFull, [StringComparison]::OrdinalIgnoreCase)) {
                throw "bundle contains an archive traversal path"
            }
        }
        if ($names.Count -ne 2 -or $names -notcontains "bundle-manifest.json") {
            throw "bundle inventory is not the reviewed two-file offline payload"
        }
        foreach ($entry in $zip.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $Destination $entry.FullName))
            $parent = Split-Path -Parent $target
            [IO.Directory]::CreateDirectory($parent) | Out-Null
            $input = $entry.Open()
            try {
                $output = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try { $input.CopyTo($output) } finally { $output.Dispose() }
            } finally { $input.Dispose() }
        }
    } finally { $zip.Dispose() }
}

if (-not $env:LOCALAPPDATA) {
    throw "LOCALAPPDATA is required for the user-owned Academy install directory"
}
$academyRoot = Join-Path $env:LOCALAPPDATA "ArbiterAcademy"
$installRoot = Join-Path $academyRoot $Release
Assert-PathInside -Root $academyRoot -Candidate $installRoot
if (Test-Path -LiteralPath $academyRoot) {
    if (-not (Test-PlainDirectory $academyRoot)) {
        throw "Academy tools directory cannot be a reparse point or non-directory"
    }
    $rootCreated = $false
} else {
    New-Item -ItemType Directory -Path $academyRoot -ErrorAction Stop | Out-Null
    $rootCreated = $true
}
if (Test-Path -LiteralPath $installRoot) {
    throw "conflicting or unowned install path: $installRoot"
}

$ownershipToken = New-OwnershipToken
$markerName = ".academy-install-owner"
$nonce = [Guid]::NewGuid().ToString("N")
$workRoot = Join-Path $academyRoot ".$Release-$nonce-work"
New-Item -ItemType Directory -Path $workRoot -ErrorAction Stop | Out-Null
$workMarker = Join-Path $workRoot $markerName
Write-OwnershipMarker -Path $workMarker -Token $ownershipToken
$downloadPath = Join-Path $workRoot $ArchiveName
$extractRoot = Join-Path $workRoot "bundle"
Assert-PathInside -Root $academyRoot -Candidate $workRoot
$ownsInstall = $false
$complete = $false

try {
    if ($BundlePath) {
        $bundle = (Resolve-Path -LiteralPath $BundlePath -ErrorAction Stop).Path
        if ((Get-Item -LiteralPath $bundle -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "local bundle must be a regular file, not a reparse point"
        }
    } else {
        Get-ImmutableReleaseAsset -Url $AssetUrl -Destination $downloadPath
        $bundle = $downloadPath
    }
    $actualDigest = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualDigest -cne $BundleSha256) {
        throw "bundle SHA-256 mismatch; extraction was not attempted"
    }

    [IO.Directory]::CreateDirectory($extractRoot) | Out-Null
    Expand-ReviewedBundle -Archive $bundle -Destination $extractRoot
    $manifestPath = Join-Path $extractRoot "bundle-manifest.json"
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.format_version -ne 1 -or $manifest.release -cne $Release -or @($manifest.wheelhouse).Count -ne 1) {
        throw "bundle manifest does not match the reviewed release contract"
    }
    $wheelRecord = @($manifest.wheelhouse)[0]
    if ($wheelRecord.filename -notmatch '^workshop_queue-[A-Za-z0-9_.]+-py3-none-any\.whl$') {
        throw "bundle manifest contains an unapproved Academy wheel name"
    }
    $wheel = Join-Path (Join-Path $extractRoot "wheelhouse") $wheelRecord.filename
    Assert-PathInside -Root $extractRoot -Candidate $wheel
    if (-not (Test-Path -LiteralPath $wheel -PathType Leaf)) {
        throw "bundle manifest Academy wheel is missing"
    }
    $wheelItem = Get-Item -LiteralPath $wheel
    if ($wheelItem.Length -ne [int64]$wheelRecord.size -or (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant() -cne $wheelRecord.sha256) {
        throw "bundle manifest Academy wheel digest or size mismatch"
    }

    $python = Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1
    New-Item -ItemType Directory -Path $installRoot -ErrorAction Stop | Out-Null
    $ownsInstall = $true
    $installMarker = Join-Path $installRoot $markerName
    Write-OwnershipMarker -Path $installMarker -Token $ownershipToken
    & $python.Source -m venv --copies $installRoot
    if ($LASTEXITCODE -ne 0) { throw "Python failed to create the Academy environment" }
    $venvPython = Join-Path $installRoot "Scripts\python.exe"
    $academy = Join-Path $installRoot "Scripts\arbiter-academy.exe"
    $wheelhouse = Join-Path $extractRoot "wheelhouse"
    $oldNoIndex = $env:PIP_NO_INDEX
    $oldNoCache = $env:PIP_NO_CACHE_DIR
    try {
        $env:PIP_NO_INDEX = "1"
        $env:PIP_NO_CACHE_DIR = "1"
        & $venvPython -m pip install --disable-pip-version-check --no-index --no-deps --find-links $wheelhouse $wheel
        if ($LASTEXITCODE -ne 0) { throw "offline Academy wheel installation failed" }
    } finally {
        $env:PIP_NO_INDEX = $oldNoIndex
        $env:PIP_NO_CACHE_DIR = $oldNoCache
    }

    $ownedPaths = @(
        Get-ChildItem -LiteralPath $installRoot -Recurse -Force | ForEach-Object {
            if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Academy environment contains an unowned reparse point"
            }
            $_.FullName.Substring($installRoot.Length + 1).Replace("\", "/")
        } | Sort-Object
    ) + "install-manifest.json"
    $installManifest = [ordered]@{
        bundle_sha256 = $BundleSha256
        executable = "Scripts/arbiter-academy.exe"
        format_version = 1
        owned_paths = $ownedPaths
        release = $Release
    }
    $manifestJson = $installManifest | ConvertTo-Json -Compress -Depth 4
    [IO.File]::WriteAllText((Join-Path $installRoot "install-manifest.json"), $manifestJson + "`n", (New-Object Text.UTF8Encoding($false)))
    $complete = $true
    Write-Output "Installed Arbiter Academy $Release at $academy"
    & $academy --repository (Get-Location).Path doctor
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Academy Doctor reported repository preconditions that need attention."
    }
} finally {
    if (Test-Path -LiteralPath $workRoot) {
        Remove-OwnedDirectory -AcademyRoot $academyRoot -Directory $workRoot -Marker $workMarker -Token $ownershipToken -Label "installer work directory"
    }
    if (-not $complete -and $ownsInstall -and (Test-Path -LiteralPath $installRoot)) {
        Remove-OwnedDirectory -AcademyRoot $academyRoot -Directory $installRoot -Marker $installMarker -Token $ownershipToken -Label "install directory"
    }
    if ($rootCreated -and (Test-PlainDirectory $academyRoot) -and -not (Get-ChildItem -LiteralPath $academyRoot -Force)) {
        Remove-Item -LiteralPath $academyRoot -Force
    }
}
