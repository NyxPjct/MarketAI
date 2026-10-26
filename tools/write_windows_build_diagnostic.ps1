param([Parameter(Mandatory=$true)][string]$Log, [Parameter(Mandatory=$true)][string]$Report)
$ErrorActionPreference = 'Stop'
# Publish only whitelisted metadata, never raw build logs or environment values.
$text = if (Test-Path $Log) { Get-Content $Log -Raw } else { '' }
$phases = [regex]::Matches($text, '\[([1-9])/9\]')
$phase = if ($phases.Count) { [int]$phases[-1].Groups[1].Value } else { 0 }
function Python-Version([string]$Command, [string[]]$Options) {
  try {
    $value = (& $Command @Options 2>$null | Out-String)
    $match = [regex]::Match($value, 'Python [0-9]+\.[0-9]+\.[0-9]+')
    if ($match.Success) { return $match.Value }
  } catch { }
  return 'unavailable'
}
$known = @('UnicodeDecodeError','SyntaxError','ModuleNotFoundError','ImportError','subprocess-exited-with-error','No matching distribution found','Failed building wheel','No module named','PYTHON_CMD','was unexpected at this time')
$markers = @($known | Where-Object { $text.Contains($_) })
$failedTests = @([regex]::Matches($text, 'FAILED (tests[/\\][A-Za-z0-9_.]+::[A-Za-z0-9_]+)') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
$packages = @([regex]::Matches($text, '(?:No matching distribution found for|Could not find a version that satisfies the requirement) ([A-Za-z0-9_.=<>!,-]+)') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
$result = [ordered]@{
  version=$env:RELEASE_VERSION; status='failed'; phase=$phase
  active_python=(Python-Version 'python' @('--version'))
  launcher_python=(Python-Version 'py' @('-3','--version'))
  markers=$markers; failed_tests=$failedTests; unresolved_packages=$packages
}
$result | ConvertTo-Json -Depth 5 | Set-Content $Report -Encoding utf8
