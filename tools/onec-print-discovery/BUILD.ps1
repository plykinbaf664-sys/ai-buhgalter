param([string]$DesignerPath)
$ErrorActionPreference = 'Stop'
$PackageRoot = $PSScriptRoot
$RepositoryRoot = [IO.Path]::GetFullPath((Join-Path $PackageRoot '../..'))
$Python = Join-Path $RepositoryRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python)) { $Python = 'python' }
& $Python (Join-Path $PackageRoot 'preflight.py')
if ($LASTEXITCODE -ne 0) { throw 'Source preflight failed' }
if (-not $DesignerPath) {
    $Candidates = @()
    foreach ($ProgramRoot in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        foreach ($Edition in @('1cv8', '1cv8t')) {
            $InstallRoot = Join-Path $ProgramRoot $Edition
            if (Test-Path -LiteralPath $InstallRoot) {
                foreach ($Version in Get-ChildItem -LiteralPath $InstallRoot -Directory) {
                    $Executable = Join-Path $Version.FullName ('bin/' + $Edition + '.exe')
                    if (Test-Path -LiteralPath $Executable) {
                        $Candidates += [PSCustomObject]@{Path=$Executable; Version=$Version.Name}
                    }
                }
            }
        }
    }
    $Chosen = $Candidates | Sort-Object {try {[version]$_.Version} catch {[version]'0.0'}} -Descending | Select-Object -First 1
    if (-not $Chosen) { throw 'Genuine 1C Designer not found; source package only' }
    $DesignerPath = $Chosen.Path
}
$PrivateRoot = Join-Path $RepositoryRoot '.local/firstbit/print-discovery'
$BuildRoot = Join-Path $PrivateRoot ('build-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
$Infobase = Join-Path $BuildRoot 'empty-infobase'
New-Item -ItemType Directory -Path $Infobase | Out-Null
$CreateLog = Join-Path $BuildRoot 'create.log'
$BuildLog = Join-Path $BuildRoot 'build.log'
$Output = Join-Path $BuildRoot 'OneCInvoicePrintDiscovery.epf'
$Source = Join-Path $PackageRoot 'src/OneCInvoicePrintDiscovery.xml'
Write-Host "Designer: $DesignerPath"
$Process = Start-Process -FilePath $DesignerPath -WindowStyle Hidden -PassThru -ArgumentList @('CREATEINFOBASE', ('"File=""' + $Infobase + '"";"'), '/DisableStartupDialogs', '/Out', ('"' + $CreateLog + '"'))
if (-not $Process.WaitForExit(120000)) { throw 'Empty local infobase creation timed out; inspect build directory' }
if (-not (Test-Path -LiteralPath (Join-Path $Infobase '1Cv8.1CD'))) { throw "Local empty infobase was not created: $CreateLog" }
$Process = Start-Process -FilePath $DesignerPath -WindowStyle Hidden -PassThru -ArgumentList @('DESIGNER', '/F', ('"' + $Infobase + '"'), '/DisableStartupDialogs', '/LoadExternalDataProcessorOrReportFromFiles', ('"' + $Source + '"'), ('"' + $Output + '"'), '/Out', ('"' + $BuildLog + '"'))
if (-not $Process.WaitForExit(120000)) { throw 'Designer import timed out; inspect build directory' }
$LogText = if (Test-Path -LiteralPath $BuildLog) { Get-Content -LiteralPath $BuildLog -Raw -Encoding UTF8 } else { '' }
if (-not (Test-Path -LiteralPath $Output) -or (Get-Item -LiteralPath $Output).Length -eq 0 -or -not $LogText.Trim()) { throw "No verified compiled artifact/log: $BuildLog" }
if ($LogText -match '(?i)error|\u043e\u0448\u0438\u0431|\u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d|\u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c') { throw "Designer log contains an error: $BuildLog" }
if ($LogText -notmatch '(?i)load[^\r\n]*(complet|finish)|\u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430') { throw "Designer completion not confirmed: $BuildLog" }
$Delivery = Join-Path $PrivateRoot 'OneCInvoicePrintDiscovery.epf'
Copy-Item -LiteralPath $Output -Destination $Delivery -Force
@{designer=$DesignerPath; source_format='2.14'; compiled=$true; live_run=$false; build_root=$BuildRoot; artifact_sha256=(Get-FileHash -LiteralPath $Delivery -Algorithm SHA256).Hash; log=$BuildLog} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PrivateRoot 'build-result.json') -Encoding UTF8
Write-Host "Compiled by genuine 1C: $Delivery"
Write-Host 'This proves import/build only. Run in an empty local infobase before live discovery.'
