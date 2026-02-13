param(
    [Parameter(Mandatory = $true)]
    [string]$AppVersion,

    [string]$RepoOwner = "lana-info",
    [string]$RepoName = "Clipart-Generator",
    [string]$ReleaseTag = "",
    [string]$SetupFileName = "",
    [string]$SetupPath = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if ([string]::IsNullOrWhiteSpace($ReleaseTag)) {
    $ReleaseTag = "v$AppVersion"
}

if ([string]::IsNullOrWhiteSpace($SetupFileName)) {
    $SetupFileName = "ClipartGenerator-Setup-$AppVersion.exe"
}

if ([string]::IsNullOrWhiteSpace($SetupPath)) {
    $SetupPath = Join-Path $projectRoot ("release\" + $SetupFileName)
}

$sha256 = ""
if (Test-Path $SetupPath) {
    $sha256 = (Get-FileHash $SetupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "SHA256 рассчитан: $sha256"
} else {
    Write-Warning "Файл setup не найден: $SetupPath"
    Write-Warning "Поле sha256 будет оставлено пустым."
}

$downloadUrl = "https://github.com/$RepoOwner/$RepoName/releases/download/$ReleaseTag/$SetupFileName"

$versionObject = [ordered]@{
    latest_version = $AppVersion
    download_url = $downloadUrl
    sha256 = $sha256
}

$versionJsonPath = Join-Path $projectRoot "version.json"
$versionObject | ConvertTo-Json -Depth 3 | Set-Content -Path $versionJsonPath -Encoding UTF8

Write-Host "version.json обновлён: $versionJsonPath"
Write-Host "latest_version: $AppVersion"
Write-Host "download_url: $downloadUrl"