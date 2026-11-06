# Mantiene el equipo y la pantalla despiertos mientras este script corre.
# Al cerrarlo, Windows vuelve a su configuración de energía normal (no cambia nada de forma permanente).
# No evita la suspensión al cerrar la tapa: eso se configura en "Elegir el comportamiento del cierre de la tapa".

Add-Type -Namespace Win32 -Name Power -MemberDefinition @'
[DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
'@

$ES_CONTINUOUS       = [uint32]"0x80000000"
$ES_SYSTEM_REQUIRED  = [uint32]"0x00000001"
$ES_DISPLAY_REQUIRED = [uint32]"0x00000002"

Write-Host "Equipo y pantalla sin suspensión mientras esta ventana esté abierta."
while ($true) {
    [Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_DISPLAY_REQUIRED) | Out-Null
    Start-Sleep -Seconds 60
}
