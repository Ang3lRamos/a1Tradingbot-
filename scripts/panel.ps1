# Genera el panel de los bots (~\.mt5bot\panel.html) y lo abre en el navegador.
# Uso: clic derecho -> "Ejecutar con PowerShell", o desde la carpeta del proyecto: .\scripts\panel.ps1
# Solo lee datos (MT5 y bitácoras): no toca las operaciones de los bots.
$project = Split-Path -Parent $PSScriptRoot
Set-Location $project
& "$env:USERPROFILE\.venvs\mt5bot\Scripts\python.exe" -m mt5bot.main panel
