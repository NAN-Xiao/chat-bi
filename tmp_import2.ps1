try {
    Install-Module -Name Posh-SSH -Scope CurrentUser -Force -AllowClobber -ErrorAction SilentlyContinue
} catch {
    # ignore
}
Import-Module Posh-SSH -ErrorAction Stop
$pwdPlain = 'ELEXtech%0609'
$sec = ConvertTo-SecureString $pwdPlain -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential('root', $sec)
$sftp = New-SFTPSession -ComputerName 10.1.5.28 -Credential $cred -AcceptKey -ErrorAction Stop
$sftpId = $sftp.SessionId
Set-SFTPFile -SessionId $sftpId -LocalFile 'C:\Users\elex\Downloads\mock.sql' -RemotePath '/tmp/mock.sql' -ErrorAction Stop
$ssh = New-SSHSession -ComputerName 10.1.5.28 -Credential $cred -AcceptKey -ErrorAction Stop
$sshId = $ssh.SessionId
$out = Invoke-SSHCommand -SessionId $sshId -Command \"PGPASSWORD='Password123@pg' psql -U postgres -tAc \\\"SELECT 1 FROM pg_database WHERE datname='slg_bi_mock'\\\"\" -ErrorAction Stop
if ($out.Output -notlike '*1*') {
    Invoke-SSHCommand -SessionId $sshId -Command \"PGPASSWORD='Password123@pg' createdb -U postgres slg_bi_mock\" -ErrorAction Stop
}
Invoke-SSHCommand -SessionId $sshId -Command \"PGPASSWORD='Password123@pg' psql -U postgres -d slg_bi_mock -f /tmp/mock.sql\" -ErrorAction Stop
Write-Output 'IMPORT_COMPLETE'
Remove-SFTPSession -SessionId $sftpId -ErrorAction SilentlyContinue
Remove-SSHSession -SessionId $sshId -ErrorAction SilentlyContinue
