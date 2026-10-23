# Signs Windows programs and installers with the project's code-signing certificate. SIGNING.md
# says how to set it up. The workflows call this only when the Windows secrets exist; without
# them every build stays as it was.
#
#   pwsh .github/scripts/win-sign.ps1 [-SkipSigned] <file.exe> [<file.exe> ...]
#
# Reads WINDOWS_CERT_PFX (the .pfx certificate file in base64) and WINDOWS_CERT_PASSWORD.
# Signs with SHA-256 and an RFC 3161 timestamp, so signatures stay good after the certificate
# expires, then checks each file carries the certificate's signature and a timestamp.
# -SkipSigned leaves files that already have a signature as they are. A path may use wildcards.
# Only a certificate exported as a .pfx works here; SIGNING.md covers the other kinds.
[CmdletBinding()]
param(
    [switch] $SkipSigned,
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]] $Path
)
$ErrorActionPreference = 'Stop'

$TimestampServers = @(
    'http://timestamp.digicert.com',
    'http://timestamp.sectigo.com',
    'http://timestamp.globalsign.com/tsa/r6advanced1'
)

# signtool.exe comes with the Windows SDK, under Windows Kits\10\bin\<version>\<arch>\: take the
# newest. SIGNTOOL in the environment overrides the search.
function Find-SignTool {
    if ($env:SIGNTOOL -and (Test-Path -LiteralPath $env:SIGNTOOL)) { return $env:SIGNTOOL }
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
    $found = @()
    foreach ($programs in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if (-not $programs) { continue }
        $bin = Join-Path $programs 'Windows Kits\10\bin'
        if (-not (Test-Path -LiteralPath $bin)) { continue }
        foreach ($dir in Get-ChildItem -LiteralPath $bin -Directory) {
            $version = $null
            if (-not [version]::TryParse($dir.Name, [ref]$version)) { continue }
            foreach ($a in @($arch, 'x64', 'x86')) {
                $exe = Join-Path $dir.FullName "$a\signtool.exe"
                if (Test-Path -LiteralPath $exe) {
                    $found += [pscustomobject]@{ Version = $version; Path = $exe }
                    break
                }
            }
        }
        $flat = Join-Path $bin "$arch\signtool.exe"  # older SDKs keep it straight under bin
        if (Test-Path -LiteralPath $flat) { $found += [pscustomobject]@{ Version = [version]'0.0'; Path = $flat } }
    }
    if ($found) { return ($found | Sort-Object Version -Descending | Select-Object -First 1).Path }
    $onPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $kit = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\App Certification Kit\signtool.exe'
    if (Test-Path -LiteralPath $kit) { return $kit }
    throw "Couldn't find signtool.exe. Install the Windows SDK, or set SIGNTOOL to its path."
}

if (-not $env:WINDOWS_CERT_PFX) {
    throw 'WINDOWS_CERT_PFX is not set. It holds the .pfx certificate in base64 (see SIGNING.md).'
}
$password = "$env:WINDOWS_CERT_PASSWORD"
$tempDir = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$pfx = Join-Path $tempDir ("signing-" + [guid]::NewGuid().ToString('N') + '.pfx')
try {
    try {
        [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String(($env:WINDOWS_CERT_PFX -replace '\s', '')))
    } catch {
        throw 'WINDOWS_CERT_PFX is not base64. Make it with: [Convert]::ToBase64String([IO.File]::ReadAllBytes("certificate.pfx")) | Set-Clipboard'
    }
    # The certificate with its private key, to check each signature against.
    $certs = [Security.Cryptography.X509Certificates.X509Certificate2Collection]::new()
    try {
        $certs.Import($pfx, $password, [Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet)
    } catch {
        throw "Couldn't open WINDOWS_CERT_PFX with the password in WINDOWS_CERT_PASSWORD: $($_.Exception.Message)"
    }
    $cert = $certs | Where-Object { $_.HasPrivateKey } | Select-Object -First 1
    if (-not $cert) { throw 'WINDOWS_CERT_PFX holds no certificate with its private key. Export it again with the private key.' }
    Write-Host "Certificate: $($cert.Subject), thumbprint $($cert.Thumbprint), good until $($cert.NotAfter.ToString('yyyy-MM-dd'))"
    if ($cert.NotAfter -lt (Get-Date)) { throw "The certificate expired on $($cert.NotAfter.ToString('yyyy-MM-dd')). Renew it and update WINDOWS_CERT_PFX." }

    $signtool = Find-SignTool
    Write-Host "signtool: $signtool"

    $files = foreach ($p in $Path) {
        if (Test-Path -LiteralPath $p) { (Resolve-Path -LiteralPath $p).Path }
        else {
            $matched = @(Resolve-Path -Path $p -ErrorAction SilentlyContinue)
            if (-not $matched) { throw "Nothing to sign at $p" }
            $matched.Path
        }
    }
    foreach ($file in $files) {
        $name = Split-Path -Leaf $file
        if ($SkipSigned -and (Get-AuthenticodeSignature -LiteralPath $file).Status -ne 'NotSigned') {
            Write-Host "${name}: already signed, kept as it is"
            continue
        }
        $done = $false
        foreach ($round in 1..3) {
            foreach ($server in $TimestampServers) {
                $signArgs = @('sign', '/f', $pfx)
                if ($password) { $signArgs += @('/p', $password) }
                $signArgs += @('/fd', 'SHA256', '/tr', $server, '/td', 'SHA256', $file)
                $ErrorActionPreference = 'Continue'  # signtool's messages on stderr aren't errors
                $out = & $signtool @signArgs 2>&1 | Out-String
                $ErrorActionPreference = 'Stop'
                if ($LASTEXITCODE -eq 0) { $done = $true; break }
                Write-Host "signtool couldn't sign $name with the timestamp server $server (try $round): $($out.Trim())"
                Start-Sleep -Seconds (5 * $round)
            }
            if ($done) { break }
        }
        if (-not $done) { throw "Couldn't sign $name" }

        $sig = Get-AuthenticodeSignature -LiteralPath $file
        if (-not $sig.SignerCertificate -or $sig.SignerCertificate.Thumbprint -ne $cert.Thumbprint) {
            throw "$name isn't signed with the certificate after signing"
        }
        if (-not $sig.TimeStamperCertificate) { throw "$name has no timestamp" }
        Write-Host "Signed ${name}: $($sig.SignerCertificate.Subject), timestamped by $($sig.TimeStamperCertificate.Subject). Windows says: $($sig.Status)"
        if ($sig.Status -ne 'Valid') {
            Write-Host "::warning title=Signing::Windows doesn't trust the signature on ${name}: $($sig.StatusMessage)"
        }
    }
} finally {
    Remove-Item -LiteralPath $pfx -Force -ErrorAction SilentlyContinue
}
