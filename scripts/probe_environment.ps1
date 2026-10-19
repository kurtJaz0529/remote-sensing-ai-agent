param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor
$pro = Get-ItemProperty 'HKLM:\SOFTWARE\ESRI\ArcGISPro' -ErrorAction SilentlyContinue
$report = [ordered]@{
    observed_at = (Get-Date).ToUniversalTime().ToString('o')
    scope = 'Read-only installation and host inventory; license and processing require separate probes'
    os = @{caption=$os.Caption; version=$os.Version; architecture=$os.OSArchitecture}
    resources = @{memory_bytes=[long]$os.TotalVisibleMemorySize * 1024; cpu=$cpu.Name; logical_processors=$cpu.NumberOfLogicalProcessors}
    arcgis = @{install_dir=$pro.InstallDir; registered_version=$pro.Version; license_status='unknown'}
    envi = @{engine_exists=(Test-Path -LiteralPath 'C:\Program Files\Harris\ENVI56\IDL88\bin\bin.x86_64\taskengine.exe'); license_status='unknown'}
    desktop = @{interactive=[Environment]::UserInteractive; window_identity='not_verified'; screenshot='not_verified'}
    disks = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { @{drive=$_.Name; free_bytes=$_.Free} })
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding utf8
