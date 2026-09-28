#Requires -Version 5.1
<#
.SYNOPSIS
  Seed airc-console home for unattended install (FR #277).
.DESCRIPTION
  - operators.txt (if missing)
  - ergo.password from fleet secret (never invent)
  - console.password GUID mint if missing (#271)
#>

function Get-AircErgoServerPassCandidate {
    param(
        [hashtable]$EnvMap = $null,
        [string]$UserProfile = $env:USERPROFILE
    )
    if (-not $EnvMap) {
        $EnvMap = @{
            AIRC_CONSOLE_SERVER_PASSWORD = $env:AIRC_CONSOLE_SERVER_PASSWORD
            AGENTIC_IRC_PASSWORD         = $env:AGENTIC_IRC_PASSWORD
            AIRC_CONSOLE_PASSWORD        = $env:AIRC_CONSOLE_PASSWORD
        }
    }
    foreach ($k in @('AIRC_CONSOLE_SERVER_PASSWORD', 'AGENTIC_IRC_PASSWORD', 'AIRC_CONSOLE_PASSWORD')) {
        $v = [string]$EnvMap[$k]
        if ($v -and $v.Trim()) { return $v.Trim() }
    }
    $candidates = @(
        (Join-Path $UserProfile '.grok\ergo\connect.password'),
        (Join-Path $UserProfile '.airc-console\ergo.password')
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) {
            $t = (Get-Content -LiteralPath $c -Raw -ErrorAction SilentlyContinue)
            if ($t -and $t.Trim()) { return $t.Trim() }
        }
    }
    return $null
}

function Initialize-AircConsoleHome {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ConsoleHome,
        [string[]]$Operators = @('Simon'),
        [hashtable]$EnvMap = $null,
        [string]$UserProfile = $env:USERPROFILE,
        [switch]$MintNickServ
    )
    New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null
    $opsFile = Join-Path $ConsoleHome 'operators.txt'
    if (-not (Test-Path -LiteralPath $opsFile) -and $Operators.Count -gt 0) {
        Set-Content -LiteralPath $opsFile -Value ($Operators -join "`n") -Encoding utf8
    }
    $ergoFile = Join-Path $ConsoleHome 'ergo.password'
    $seededErgo = $false
    if (-not (Test-Path -LiteralPath $ergoFile)) {
        $pass = Get-AircErgoServerPassCandidate -EnvMap $EnvMap -UserProfile $UserProfile
        if ($pass) {
            Set-Content -LiteralPath $ergoFile -Value $pass -Encoding utf8
            $seededErgo = $true
        }
    }
    $nickFile = Join-Path $ConsoleHome 'console.password'
    $mintedNick = $false
    if ($MintNickServ -or -not (Test-Path -LiteralPath $nickFile)) {
        if (-not (Test-Path -LiteralPath $nickFile) -or [string]::IsNullOrWhiteSpace((Get-Content -LiteralPath $nickFile -Raw -ErrorAction SilentlyContinue))) {
            $guid = [guid]::NewGuid().ToString()
            Set-Content -LiteralPath $nickFile -Value $guid -Encoding utf8
            $mintedNick = $true
        }
    }
    return [pscustomobject]@{
        ConsoleHome     = $ConsoleHome
        OperatorsFile   = $opsFile
        ErgoPassword    = $ergoFile
        NickServFile    = $nickFile
        SeededErgo      = $seededErgo
        MintedNickServ  = $mintedNick
        OperatorsPresent = (Test-Path -LiteralPath $opsFile)
        ErgoPresent     = (Test-Path -LiteralPath $ergoFile)
        NickServPresent = (Test-Path -LiteralPath $nickFile)
    }
}
