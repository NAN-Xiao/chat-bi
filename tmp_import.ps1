try {
    Install-Module -Name Posh-SSH -Scope CurrentUser -Force -AllowClobber -ErrorAction SilentlyContinue
} catch {
    # ignore
}
Import-Module Posh-SSH -ErrorAction Stop
$pwdPlain = 'ELEXtech%0609'
$sec = ConvertTo-SecureString $pwdPlain -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential('root', $sec)
$s = New-SSHSession -ComputerName 10.1.5.28 -Credential $cred -AcceptKey -ErrorAction Stop
$sid = $s.SessionId
Set-SCPFile -LocalFile 'C:\Users\elex\Downloads\mock.sql' -RemotePath '/tmp/mock.sql' -SessionId $sid -ErrorAction Stop
$out = Invoke-SSHCommand -SessionId $sid -Command "PGPASSWORD='Password123@pg' psql -U postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='slg_bi_mock'\"" -ErrorAction Stop
if ($out.Output -notlike '*1*') {
    Invoke-SSHCommand -SessionId $sid -Command "PGPASSWORD='Password123@pg' createdb -U postgres slg_bi_mock" -ErrorAction Stop
}
Invoke-SSHCommand -SessionId $sid -Command "PGPASSWORD='Password123@pg' psql -U postgres -d slg_bi_mock -f /tmp/mock.sql" -ErrorAction Stop
Write-Output 'IMPORT_COMPLETE'
Remove-SSHSession -SessionId $sid -ErrorAction SilentlyContinue
