# On-Screen Pen Build Script

# Ensure dependencies are installed
Write-Host "Installing dependencies..."
pip install -r requirements.txt

# Compile to a standalone executable
Write-Host "Compiling main.py into standalone .exe..."
pyinstaller --noconsole --onefile --name "OnScreenPen" main.py

Write-Host "Build complete! The .exe can be found in the 'dist' folder."
