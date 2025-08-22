# === Nastavení ===
$driveLabel = "SD_HR"  # Název karty
$scriptPath = "N:\HR\HR\Foto_zamestnancu\ID_card_tool\scr\crop_karta.py" # Python skript
$lastDrive  = $null

# === Funkce: Najdi Python ===
function Get-PythonPath {
    try { return (Get-Command py -ErrorAction Stop).Source }
    catch {
        try { return (Get-Command python -ErrorAction Stop).Source }
        catch {
            Write-Host "[CHYBA] Python nebyl nalezen. Přidej ho do PATH nebo nainstaluj." -ForegroundColor Red
            exit 1
        }
    }
}

$pythonPath = Get-PythonPath
Write-Host "[INFO] Používám Python: $pythonPath" -ForegroundColor Cyan

# === Čekání na síť a dostupnost disku N ===
Write-Host "[HLÍDÁNÍ] Čekám na připojení sítě a disku N: ..." -ForegroundColor Yellow
while (-not (Test-Path "N:\")) {
    Start-Sleep -Seconds 5
}
Write-Host "[INFO] Disk N: je dostupný, pokračuji." -ForegroundColor Green

# === Hlavní smyčka ===
while ($true) {
    $drive = Get-WmiObject Win32_LogicalDisk | Where-Object { $_.VolumeName -eq $driveLabel } | Select-Object -First 1

    if ($drive -and -not $lastDrive) {
        # Nově připojeno
        $driveLetter = $drive.DeviceID
        Write-Host "[INFO] Detekována karta '$driveLabel' na $driveLetter" -ForegroundColor Green

        try {
            & $pythonPath $scriptPath $driveLetter
        }
        catch {
            Write-Host "[CHYBA] Nepodařilo se spustit Python skript: $_" -ForegroundColor Red
        }
        $lastDrive = $driveLetter
    }
    elseif (-not $drive -and $lastDrive) {
        # Byla odpojena
        Write-Host "[INFO] Karta '$driveLabel' byla odpojena." -ForegroundColor DarkYellow
        $lastDrive = $null
    }

    Start-Sleep -Seconds 3
}
