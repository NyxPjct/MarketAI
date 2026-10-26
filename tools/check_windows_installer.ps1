param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [Parameter(Mandatory=$true)][string]$ExpectedVersion,
  [Parameter(Mandatory=$true)][string]$Report
)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP ('MarketAI installer checks ' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $root -Force | Out-Null
$result = [ordered]@{ version=$ExpectedVersion; status='running'; clean_install=$false; upgrade=$false; native_window=$false; data_preserved=$false; message='' }
$processIds = @()

function Install-Package([string]$Path, [string]$Destination) {
  $log = Join-Path $root ('setup-' + [guid]::NewGuid() + '.log')
  $p = Start-Process -FilePath $Path -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',('/DIR="' + $Destination + '"'),('/LOG="' + $log + '"')) -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "Installer exit code: $($p.ExitCode)" }
  if (-not (Test-Path (Join-Path $Destination 'MarketAI.exe'))) { throw 'Installed executable is missing' }
}

function Family-Ids([int]$RootId) {
  $ids = @($RootId)
  $all = @(Get-CimInstance Win32_Process)
  do {
    $next = @($all | Where-Object { $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids } | Select-Object -ExpandProperty ProcessId)
    $ids += $next
  } while ($next.Count -gt 0)
  return $ids
}

function Check-Native([string]$Directory, [string]$DataDirectory, [bool]$ExpectPreferences) {
  $env:MARKETAI_DATA_DIR = $DataDirectory
  # Tests must never contact the hosted Cloud using synthetic local session data.
  $env:MARKETAI_CLOUD_URL = 'http://127.0.0.1:9'
  $process = Start-Process -FilePath (Join-Path $Directory 'MarketAI.exe') -PassThru
  $script:processIds = @($process.Id)
  $deadline = (Get-Date).AddSeconds(60)
  $info = $null
  $url = $null
  $windowFound = $false
  try {
    while ((Get-Date) -lt $deadline) {
      $script:processIds = @(Family-Ids $process.Id)
      $connections = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $script:processIds })
      foreach ($connection in $connections) {
        try {
          $candidate = 'http://127.0.0.1:' + $connection.LocalPort
          $data = Invoke-RestMethod ($candidate + '/api/app/info') -TimeoutSec 2
          if ($data.name -eq 'MarketAI') { $info=$data; $url=$candidate; break }
        } catch { }
      }
      $windows = @(Get-Process -Id $script:processIds -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "MarketAI v$ExpectedVersion*" })
      if ($windows.Count -gt 0) { $windowFound=$true }
      if ($info -and $windowFound) { break }
      Start-Sleep -Milliseconds 500
    }
    if (-not $info) {
      $startup = Join-Path $DataDirectory 'logs/startup-error.log'
      $detail = if (Test-Path $startup) { ((Get-Content $startup -Raw) | Select-Object -First 1) } else { 'No startup error log' }
      throw "Installed backend did not become ready. $detail"
    }
    if ($info.version -ne $ExpectedVersion) { throw "Wrong installed version: $($info.version)" }
    if (-not $windowFound) {
      $startup = Join-Path $DataDirectory 'logs/startup-error.log'
      $detail = if (Test-Path $startup) { Get-Content $startup -Raw } else { 'No startup error log' }
      throw "The installed native window did not open with the expected title. $detail"
    }
    $html = Invoke-WebRequest ($url + '/') -UseBasicParsing -TimeoutSec 5
    if ($html.Content -notmatch 'data-view="batches"') { throw 'Installed catalog interface is missing' }
    $js = Invoke-WebRequest ($url + '/static/batches.js') -UseBasicParsing -TimeoutSec 5
    if ($js.Content -notmatch 'MarketBatches') { throw 'Packaged batch script is missing' }
    if ($html.Content -notmatch 'data-view="catalog"') { throw 'Installed SKU catalog interface is missing' }
    $catalogJs = Invoke-WebRequest ($url + '/static/catalog.js') -UseBasicParsing -TimeoutSec 5
    if ($catalogJs.Content -notmatch 'MarketCatalog') { throw 'Packaged catalog script is missing' }
    if ($html.Content -notmatch 'catalogBackupExport' -or $html.Content -notmatch 'alertRulesDialog') { throw 'Installed backup/alert interface is missing' }
    foreach ($asset in @('catalog-backup.js','alert-rules.js')) {
      $response = Invoke-WebRequest ($url + '/static/' + $asset) -UseBasicParsing -TimeoutSec 5
      if (-not $response.Content) { throw "Packaged asset is empty: $asset" }
    }
    if ($ExpectPreferences -and $info.preferences.default_margin_percent -ne 27.5) { throw 'Preferences were not preserved through upgrade' }
    $result.native_window=$true
  } finally {
    if ($script:processIds.Count -gt 0) { Stop-Process -Id $script:processIds -Force -ErrorAction SilentlyContinue }
    $script:processIds=@()
  }
}

function Uninstall-Package([string]$Directory) {
  $uninstaller = Join-Path $Directory 'unins000.exe'
  if (Test-Path $uninstaller) {
    $p=Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Uninstaller exit code: $($p.ExitCode)" }
  }
}

try {
  $Installer=(Resolve-Path $Installer).Path
  $clean = Join-Path $root 'clean install'
  Install-Package $Installer $clean
  Check-Native $clean (Join-Path $root 'clean-data') $false
  Uninstall-Package $clean
  $result.clean_install=$true

  # Verify previous official installers before using them as upgrade baselines.
  $baselines = @(
    @{ Version='1.0.5'; Sha='5a731338f2418146d022ae3bf2664f0dcb6d94b9e14b321459f774f837c149ac' },
    @{ Version='1.1.0'; Sha='2de675419ba98011d18a26afaa82287d07d5f21800f52e12e9636249d6931d67' },
    @{ Version='1.2.0'; Sha='2674c7cbc921724182bf6f8eb0cb5ccb49f8ed0ad58f2a44c709f6324e6ecb22' },
    @{ Version='1.3.0'; Sha='3f5ab1666967998b369f0cdf61bbb1866b48dda7945970042f583a61f6597a52' }
  )
  $result.upgraded_from=@()
  foreach ($entry in $baselines) {
    $version=$entry.Version
    $baseline = Join-Path $root "MarketAI-Setup-v$version.exe"
    Invoke-WebRequest "https://github.com/NyxPjct/MarketAI/releases/download/v$version/MarketAI-Setup-v$version.exe" -OutFile $baseline
    $hash=(Get-FileHash $baseline -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $entry.Sha) { throw "Baseline v$version SHA-256 mismatch" }
    $upgrade = Join-Path $root "upgrade from $version"
    $data = Join-Path $root "upgrade-data-$version"
    Install-Package $baseline $upgrade
    New-Item -ItemType Directory -Path $data -Force | Out-Null
    $preferences='{"default_margin_percent":27.5,"first_run_completed":true}'
    [IO.File]::WriteAllText((Join-Path $data 'preferences.json'),$preferences)
    [IO.File]::WriteAllText((Join-Path $data 'upgrade-marker.txt'),'preserved-user-data')
    Install-Package $Installer $upgrade
    Check-Native $upgrade $data $true
    if ((Get-Content (Join-Path $data 'upgrade-marker.txt') -Raw) -ne 'preserved-user-data') { throw 'Upgrade deleted local user data' }
    Uninstall-Package $upgrade
    $result.upgraded_from += $version
  }
  $result.upgrade=$true
  $result.data_preserved=$true
  $result.status='passed'
} catch {
  $result.status='failed'
  $result.message=$_.Exception.Message
  throw
} finally {
  if ($processIds.Count -gt 0) { Stop-Process -Id $processIds -Force -ErrorAction SilentlyContinue }
  $parent=Split-Path $Report -Parent
  if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
  $result | ConvertTo-Json | Set-Content -Path $Report -Encoding utf8
}
