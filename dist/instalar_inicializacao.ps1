# Registra a Tarefa Agendada que inicia o Monitor de TI no LOGON de qualquer
# usuario e o reabre automaticamente caso a tarefa caia.
#
# Nao precisa rodar este .ps1 direto: use "instalar_inicializacao.bat"
# (ele pede elevacao e chama este script).

$ErrorActionPreference = "Stop"

$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
$wd = Join-Path $pasta "TI Watchdog.exe"
if (-not (Test-Path $wd)) {
    Write-Host "ERRO: 'TI Watchdog.exe' nao foi encontrado nesta pasta:"
    Write-Host "      $pasta"
    exit 1
}

$taskName = "TI Monitor Manutencao"

$action = New-ScheduledTaskAction -Execute $wd

# Dispara no logon de qualquer usuario (sessao interativa -> a janela aparece).
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Grupo "Usuarios" pelo SID fixo (independe do idioma do Windows). Nivel mais alto.
$principal = New-ScheduledTaskPrincipal -GroupId "S-1-5-32-545" -RunLevel Highest

# Resiliencia: se o processo for morto, o Agendador reinicia a tarefa.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = "PT0S"   # sem limite de tempo de execucao

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host ""
Write-Host "OK! Tarefa '$taskName' criada."
Write-Host "O Monitor de TI iniciara no proximo logon e reabre sozinho se for fechado."
