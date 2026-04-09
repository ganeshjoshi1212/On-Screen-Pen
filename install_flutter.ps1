New-Item -ItemType Directory -Force -Path "C:\src" | Out-Null
Write-Host "Cloning Flutter Stable branch into C:\src\flutter... (This may take several minutes depending on your internet speed. Please wait.)"
git clone https://github.com/flutter/flutter.git -b stable C:\src\flutter

Write-Host "Updating Environment PATH..."
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*C:\src\flutter\bin*") {
    $newPath = $userPath + ";C:\src\flutter\bin"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Successfully added Flutter to your PATH!"
} else {
    Write-Host "Flutter is already in your PATH."
}

Write-Host "Installation script complete."
