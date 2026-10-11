while ($true) {
    Write-Host "Starting localtunnel on port 8000 (subdomain: proud-spoons-act)..."
    npx --yes localtunnel --port 8000 --subdomain proud-spoons-act
    Write-Host "Localtunnel disconnected. Reconnecting in 2 seconds..."
    Start-Sleep -Seconds 2
}
