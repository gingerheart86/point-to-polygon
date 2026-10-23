<#
.SYNOPSIS
  Arma el .zip instalable del plugin: dist\punto_a_poligono-<versión>.zip
.DESCRIPTION
  La versión se toma de punto_a_poligono\metadata.txt. El zip se instala en QGIS con
  Complementos → Administrar e instalar complementos → Instalar desde ZIP.
  Para publicar una versión: subir la versión en metadata.txt (y el changelog), hacer merge del PR,
  correr este script y adjuntar el zip a un Release de GitHub con el tag vX.Y.Z.
#>
$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
$pkg = Join-Path $raiz 'punto_a_poligono'
$version = (Select-String -LiteralPath "$pkg\metadata.txt" -Pattern '^version=(.+)$').Matches[0].Groups[1].Value.Trim()
# MANUAL.pdf se regenera desde MANUAL.md con el Python de QGIS, para que nunca quede desactualizado
$pyqgis = Get-ChildItem 'C:\Program Files\QGIS*\bin\python-qgis*.bat' -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1
if ($pyqgis) {
    Push-Location $env:TEMP  # el .bat corre en CMD, que no acepta rutas UNC como carpeta actual
    try { & $pyqgis.FullName (Join-Path $raiz 'generar_manual.py') } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar MANUAL.pdf' }
} else {
    Write-Warning 'No encontré QGIS: el zip lleva el MANUAL.pdf que ya estaba.'
}
$dist = Join-Path $raiz 'dist'
New-Item -ItemType Directory -Force $dist | Out-Null
$tmp = Join-Path ([IO.Path]::GetTempPath()) "empaquetar_$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory $tmp | Out-Null
Copy-Item -LiteralPath $pkg -Destination $tmp -Recurse
Get-ChildItem $tmp -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Get-ChildItem $tmp -Recurse -File -Include '*.pyc', '*.bak' | Remove-Item -Force
$zip = Join-Path $dist "punto_a_poligono-$version.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $tmp 'punto_a_poligono') -DestinationPath $zip
Remove-Item -LiteralPath $tmp -Recurse -Force
Write-Host "Listo: $zip" -ForegroundColor Green

