$ErrorActionPreference = 'Stop'
$root = 'C:\workspace\ldoce'
$dest = "$root\The little dict"
$base = 'https://downloads.freemdict.com/%E5%B0%9A%E6%9C%AA%E6%95%B4%E7%90%86/%E5%85%B1%E4%BA%AB2020.5.11/content/0_audio/The%20little%20dict/'
$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
$log = "$root\.download.log"

function Log($m) {
  $line = "$([datetime]::Now.ToString('HH:mm:ss')) $m"
  Add-Content -Path $log -Value $line -Encoding UTF8
  Write-Output $line
}

Set-Content -Path $log -Value "download run started $([datetime]::Now.ToString('u'))" -Encoding UTF8

$files = Get-Content "$root\.manifest.json" -Raw | ConvertFrom-Json
Log "START files=$($files.Count) total=$((($files | Measure-Object -Property size -Sum).Sum))"

$ok = 0
$fail = @()
foreach ($f in $files) {
  $rel = $f.rel
  $out = Join-Path $dest ($rel -replace '/', '\')
  $outDir = Split-Path $out -Parent
  if (!(Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
  if (Test-Path $out) {
    $cur = (Get-Item $out).Length
    if ($cur -eq $f.size) { Log "SKIP $rel (already complete)"; $ok++; continue }
    Log "PARTIAL $rel have=$cur want=$($f.size)"
  }
  $done = $false
  for ($attempt = 1; $attempt -le 30 -and -not $done; $attempt++) {
    $useResume = ($attempt % 2 -eq 1)
    $cargs = @('-sS', '-m', '3600', '--retry', '10', '--retry-all-errors', '--retry-delay', '3', '-A', $ua, '-o', $out)
    if ($useResume) { $cargs += @('-C', '-') }
    $cargs += ($base + ($rel -replace ' ', '%20'))
    & curl.exe @cargs
    $code = $LASTEXITCODE
    if ($code -eq 0 -and (Test-Path $out) -and (Get-Item $out).Length -eq $f.size) {
      Log "OK $rel size=$($f.size)"
      $ok++
      $done = $true
    } else {
      Log "RETRY $rel attempt=$attempt exit=$code have=$((Get-Item $out -ErrorAction SilentlyContinue).Length) want=$($f.size)"
      Start-Sleep -Seconds 3
    }
  }
  if (-not $done) { $fail += $rel; Log "FAIL $rel" }
}
Log "DONE ok=$ok fail=$($fail.Count)"
if ($fail.Count -gt 0) { Log "FAILED LIST: $($fail -join ', ')" }
Log "END"
