#!/usr/bin/env pwsh
# Build frontend with $env:EC2_API_BASE (or pass -ApiBaseUrl) and sync dist tarball to ubuntu@$Ec2Host.
param(
    [string] $Ec2Host = "18.216.190.63",
    [string] $ApiBaseUrl = "",
    [string] $SshKey = "D:\code\cursor\env\secmanus.pem",
    [string] $RemoteUser = "ubuntu"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$b = $ApiBaseUrl
if (-not $b) {
    $b = $env:EC2_API_BASE.Trim()
}
if (-not $b) {
    $b = "http://${Ec2Host}:8000"
}

$env:VITE_API_MODE = "local"
$env:VITE_LOCAL_API_URL = $b.TrimEnd('/')
Write-Host "Building with VITE_LOCAL_API_URL=$($env:VITE_LOCAL_API_URL)"
npm run build

$tgz = Join-Path $root "dist.tgz"
if (Test-Path $tgz) { Remove-Item $tgz }
tar -czf $tgz -C (Join-Path $root "dist") .

$remoteTar = "/tmp/secmanus-dist.tgz"
scp -i $SshKey $tgz "${RemoteUser}@${Ec2Host}:$remoteTar"

$bash = @"
set -e
cd ~/secmanus-workspace
rm -rf dist && mkdir dist
tar -xzf $remoteTar -C dist
chmod -R a+rX dist
curl -sI http://127.0.0.1/ | head -3
"@

ssh -i $SshKey "${RemoteUser}@${Ec2Host}" $bash
Remove-Item $tgz -ErrorAction SilentlyContinue
Write-Host "Done."
