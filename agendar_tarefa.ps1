<#
  Ativa (ou desativa) a verificacao automatica de precos no Agendador de Tarefas do Windows.

  Ativar:     powershell -ExecutionPolicy Bypass -File agendar_tarefa.ps1
  Desativar:  powershell -ExecutionPolicy Bypass -File agendar_tarefa.ps1 -Remover

  A tarefa roda a cada 15 min, sem abrir janela, ate 02/12/2026. O proprio programa
  decide se ja e hora de verificar (de 60 em 60 min; de 15 em 15 na semana da Black Friday).
  So funciona com voce logado no Windows e o PC ligado (dormindo/hibernando ele nao roda).
#>
param([switch]$Remover)

$ErrorActionPreference = "Stop"
$nome = "Monitor TV TCL C6K"  # mesmo nome usado em monitor_precos.py
$pasta = $PSScriptRoot

if ($Remover) {
    Unregister-ScheduledTask -TaskName $nome -Confirm:$false
    Write-Host "Tarefa '$nome' removida. O monitor nao roda mais sozinho."
    return
}

$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"  # pythonw = sem janela
if (-not (Test-Path $pythonw)) { throw "pythonw.exe nao encontrado ao lado de $python" }

$inicio = (Get-Date).AddMinutes(1)
$fim = Get-Date "2026-12-02T00:00:00"
if ($fim -le $inicio) { throw "A Black Friday 2026 ja passou - ajuste a data de fim neste script." }

$acao = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "`"$pasta\monitor_precos.py`" --agendado" -WorkingDirectory $pasta
$gatilho = New-ScheduledTaskTrigger -Once -At $inicio `
    -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration ($fim - $inicio)
$opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $opcoes `
    -Description "Verifica precos das TVs TCL C6K e avisa no celular (projeto c6k-tcl)." -Force | Out-Null

Write-Host "Tarefa '$nome' ativada: verifica os precos sozinha ate 02/12/2026."
Write-Host "Log: $pasta\historico\monitor.log"
