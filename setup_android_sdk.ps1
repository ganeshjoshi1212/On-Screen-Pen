$sdkRoot = "C:\src\android-sdk"
$toolsZip = "C:\src\android-sdk\tools.zip"
$toolsUrl = "https://dl.google.com/android/repository/commandlinetools-win-14742923_latest.zip"

# 1. Create directories
if (!(Test-Path $sdkRoot)) {
    New-Item -ItemType Directory -Path $sdkRoot -Force
}

# 2. Download Command-Line Tools
Write-Host "Downloading Android Command-Line Tools (approx 150MB)..."
Invoke-WebRequest -Uri $toolsUrl -OutFile $toolsZip

# 3. Extract Tools
Write-Host "Extracting tools..."
Expand-Archive -Path $toolsZip -DestinationPath "$sdkRoot\temp" -Force

# 4. Correct Folder Structure (cmdline-tools/latest)
if (!(Test-Path "$sdkRoot\cmdline-tools\latest")) {
    New-Item -ItemType Directory -Path "$sdkRoot\cmdline-tools\latest" -Force
}
Move-Item -Path "$sdkRoot\temp\cmdline-tools\*" -Destination "$sdkRoot\cmdline-tools\latest" -Force
Remove-Item -Path "$sdkRoot\temp" -Recurse -Force
Remove-Item -Path $toolsZip -Force

# 5. Set Environment Variables for this session and permanently
Write-Host "Setting ANDROID_HOME..."
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdkRoot, "User")
$env:ANDROID_HOME = $sdkRoot

# 6. Install SDK components
$sdkManager = "$sdkRoot\cmdline-tools\latest\bin\sdkmanager.bat"
Write-Host "Installing SDK components (platform-tools, build-tools, platforms)..."

# Accept licenses first
Write-Host "Accepting licenses..."
echo y | & $sdkManager --sdk_root=$sdkRoot --licenses

# Install essential components
& $sdkManager --sdk_root=$sdkRoot "platform-tools" "build-tools;34.0.0" "platforms;android-34"

Write-Host "Android SDK setup complete!"
