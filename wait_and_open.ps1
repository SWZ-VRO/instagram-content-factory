# Attend que le serveur reponde vraiment avant d'ouvrir le navigateur --
# evite le "ce site est inaccessible" quand le navigateur s'ouvrait trop
# tot, avant qu'uvicorn ait fini de demarrer.
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1 | Out-Null
        Start-Process "http://127.0.0.1:8000/demo"
        exit
    } catch {
        Start-Sleep -Seconds 1
    }
}
