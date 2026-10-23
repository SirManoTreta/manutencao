# Registra a Tarefa Agendada que roda o HEARTBEAT headless já no BOOT (como
# SYSTEM, antes do login). Faz a máquina aparecer online na tela de login e
# informa "login feito: sim/não".
#
# Use "instalar_heartbeat_boot.bat" (pede elevacao e chama este script).

$ErrorActionPreference = "Stop"

$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
$hb = Join-Path $pasta "TI Heartbeat.exe"
if (-not (Test-Path $hb)) {
    Write-Host "ERRO: 'TI Heartbeat.exe' nao foi encontrado nesta pasta:"
    Write-Host "      $pasta"
    exit 1
}

$taskName = "TI Heartbeat Boot"

$action = New-ScheduledTaskAction -Execute $hb

# Dispara ao ligar o computador (antes do login).
$trigger = New-ScheduledTaskTrigger -AtStartup

# Roda como SYSTEM (conta de serviço local), sem precisar de usuario logado.
$principal = New-ScheduledTaskPrincipal -UserId "S-1-5-18" -LogonType ServiceAccount -RunLevel Highest

# Sempre ligado: reinicia se cair, sem limite de tempo, mesmo na bateria.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = "PT0S"

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host ""
Write-Host "OK! Tarefa '$taskName' criada."
Write-Host "O heartbeat roda desde o boot (como SYSTEM) e reporta se ha login ou nao."
