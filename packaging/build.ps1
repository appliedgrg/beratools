# Beratools Windows Installer Build Script
# Run: powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Beratools Windows Installer Build ===" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Use the verified CI release version when provided; local and test builds fall back to Git.
$version = ([string]$env:APP_VERSION).Trim()
if ($version) {
    Write-Host "Version from APP_VERSION: $version" -ForegroundColor Green
} else {
    $version = (git describe --tags --abbrev=0 2>$null)
    if (-not $version) {
        $version = "0.0.0"
        Write-Host "No git tag found, using default version: $version" -ForegroundColor Yellow
    } else {
        $version = $version.TrimStart('v')
        Write-Host "Version from git tag: $version" -ForegroundColor Green
    }
}
$env:APP_VERSION = $version

# Step 1: Create directories
Write-Host "`n[1/9] Creating build directories..." -ForegroundColor Yellow

$buildDir = Join-Path $scriptDir "build"
New-Item -Path $buildDir -ItemType Directory -Force | Out-Null

# Step 2: Download Python Embedded
Write-Host "`n[2/9] Downloading Python 3.11 Embedded Distribution..." -ForegroundColor Yellow

if (-not (Test-Path (Join-Path $buildDir "python\python.exe"))) {
    # Find latest Python 3.11.x version with embeddable distribution
    Write-Host "Finding latest Python 3.11.x version..."
    $ftpListing = Invoke-WebRequest -Uri "https://www.python.org/ftp/python/" -UseBasicParsing
    $versions = [regex]::Matches($ftpListing.Content, 'href="(3\.11\.\d+)/"') | 
        ForEach-Object { $_.Groups[1].Value } | 
        Sort-Object { [version]$_ } -Descending
    
    if ($versions.Count -eq 0) {
        Write-Host "Failed to find Python 3.11.x versions" -ForegroundColor Red
        exit 1
    }
    
    $pythonZip = "python.zip"
    $foundVersion = $null
    
    foreach ($pyVersion in $versions) {
        $pythonUrl = "https://www.python.org/ftp/python/$pyVersion/python-$pyVersion-embed-amd64.zip"
        try {
            Invoke-WebRequest -Uri $pythonUrl -Method Head -UseBasicParsing -ErrorAction Stop | Out-Null
            Write-Host "Downloading Python $pyVersion from $pythonUrl..."
            Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip -Verbose
            $foundVersion = $pyVersion
            break
        } catch {
            Write-Host "Python $pyVersion embed not available, trying older version..." -ForegroundColor Yellow
        }
    }
    
    if (-not $foundVersion) {
        Write-Host "Failed to find any Python 3.11.x embeddable distribution" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Extracting to build\python..."
    Expand-Archive -Path $pythonZip -DestinationPath (Join-Path $buildDir "python") -Force
    
    Remove-Item $pythonZip
    Write-Host "Python $foundVersion installed successfully" -ForegroundColor Green
} else {
    Write-Host "Python already exists, skipping download" -ForegroundColor Green
}

# Step 3: Enable pip in embedded Python and add beratools to path
Write-Host "`n[3/9] Configuring embedded Python path..." -ForegroundColor Yellow

$pthFile = Get-ChildItem (Join-Path $buildDir "python\python*._pth") | Select-Object -First 1
if ($pthFile) {
    $zipName = [System.IO.Path]::GetFileNameWithoutExtension($pthFile.Name) + ".zip"
    @"
$zipName
.
..
import site
"@ | Set-Content -Path $pthFile.FullName
    Write-Host "Configured Python path with beratools parent directory" -ForegroundColor Green
}

# Step 4: Install pip
Write-Host "`n[4/9] Installing pip..." -ForegroundColor Yellow

if (-not (Test-Path (Join-Path $buildDir "python\Scripts\pip.exe"))) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "get-pip.py" -Verbose
    & (Join-Path $buildDir "python\python.exe") get-pip.py --quiet
    Remove-Item "get-pip.py"
    Write-Host "Pip installed" -ForegroundColor Green
} else {
    Write-Host "Pip already exists, skipping" -ForegroundColor Green
}

# Step 5: Install dependencies from pyproject.toml
Write-Host "`n[5/9] Installing Python dependencies..." -ForegroundColor Yellow


$pyprojectPath = Join-Path $scriptDir "..\pyproject.toml"
$pyprojectPath = [System.IO.Path]::GetFullPath($pyprojectPath)
$pyproject = Get-Content $pyprojectPath -Raw

# Extract GDAL URL (prefer env var, then [tool.beratools] gdal_url, then legacy regex)
$gdalUrl = $env:BERATOOLS_GDAL_URL
if (-not $gdalUrl -and $pyproject -match '(?m)^\s*\[tool\.beratools\]\s*$([\s\S]*?)(?=^\s*\[|\z)') {
    $toolBlock = $Matches[1]
    if ($toolBlock -match '(?m)^\s*gdal_url\s*=\s*"([^"]+)"\s*$') {
        $gdalUrl = $Matches[1]
    }
}
if (-not $gdalUrl -and $pyproject -match 'gdal\s*@\s*(https://[^\s;]+\.whl)') {
    $gdalUrl = $Matches[1]
}

if ($gdalUrl) {
    Write-Host "Installing GDAL wheel from $gdalUrl..."
    & (Join-Path $buildDir "python\python.exe") -m pip install $gdalUrl --quiet --no-warn-script-location
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install GDAL" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Failed to extract GDAL URL from pyproject.toml or BERATOOLS_GDAL_URL" -ForegroundColor Red
    exit 1
}

# Extract dependencies from pyproject.toml
if ($pyproject -match '(?s)dependencies\s*=\s*\[(.*?)\]') {
    $depsBlock = $Matches[1]
    $deps = [regex]::Matches($depsBlock, '"([^"]+)"') | 
        ForEach-Object { $_.Groups[1].Value } |
        Where-Object { $_ -notmatch 'gdal' }  # Skip gdal, already installed
    
    Write-Host "Installing dependencies: $($deps -join ', ')"
    & (Join-Path $buildDir "python\python.exe") -m pip install @deps --quiet --no-warn-script-location
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Failed to extract dependencies from pyproject.toml" -ForegroundColor Red
    exit 1
}
Write-Host "Dependencies installed" -ForegroundColor Green

# Step 6: Ensure GDAL/PROJ data assets are present
Write-Host "`n[6/9] Validating GDAL/PROJ data assets..." -ForegroundColor Yellow
$sitePackages = Join-Path $buildDir "python\Lib\site-packages"
$projDb = Join-Path $sitePackages "osgeo\data\proj\proj.db"
if (-not (Test-Path $projDb)) {
    Write-Host "proj.db not found at $projDb" -ForegroundColor Red
    exit 1
}
$gdalData = Join-Path $sitePackages "osgeo\data\gdal"
if (-not (Test-Path $gdalData)) {
    Write-Host "GDAL data directory not found at $gdalData" -ForegroundColor Red
    exit 1
}
Write-Host "GDAL/PROJ data assets found" -ForegroundColor Green

# Step 7: Build Go launcher with version info + icon
Write-Host "`n[7/9] Building Go launcher..." -ForegroundColor Yellow

if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
    Write-Host "Go not found in PATH. Please install Go 1.21+" -ForegroundColor Red
    exit 1
}

Set-Location $scriptDir

$iconPath = Join-Path $scriptDir "..\beratools\gui\assets\BERALogo.ico"
if (-not (Test-Path $iconPath)) {
    Write-Host "Launcher icon not found at $iconPath" -ForegroundColor Red
    exit 1
}

$versionParts = $version.Split('.')
while ($versionParts.Count -lt 3) { $versionParts += "0" }
$verMajor = [int]$versionParts[0]
$verMinor = [int]$versionParts[1]
$verPatch = [int]$versionParts[2]
$verBuild = 0
$fileVersion = "$verMajor.$verMinor.$verPatch.$verBuild"

$versionInfoJson = @"
{
  "FixedFileInfo": {
    "FileVersion": {
      "Major": $verMajor,
      "Minor": $verMinor,
      "Patch": $verPatch,
      "Build": $verBuild
    },
    "ProductVersion": {
      "Major": $verMajor,
      "Minor": $verMinor,
      "Patch": $verPatch,
      "Build": $verBuild
    }
  },
  "StringFileInfo": {
    "CompanyName": "BERA Tools",
    "FileDescription": "BERA Tools Launcher",
    "FileVersion": "$fileVersion",
    "InternalName": "beratools",
    "OriginalFilename": "beratools.exe",
    "ProductName": "BERA Tools",
    "ProductVersion": "$fileVersion"
  }
}
"@

$versionInfoPath = Join-Path $scriptDir "versioninfo.json"
$versionInfoJson | Set-Content -Path $versionInfoPath -Encoding ASCII

Write-Host "Generating Windows version resource..."
& go run github.com/josephspurrier/goversioninfo/cmd/goversioninfo@v1.4.0 -icon $iconPath -o (Join-Path $scriptDir "resource.syso")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to generate version resource" -ForegroundColor Red
    exit 1
}

go build -ldflags "-H=windowsgui" -o (Join-Path $buildDir "beratools.exe") main.go
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to build Go launcher" -ForegroundColor Red
    exit 1
}
Write-Host ("Go launcher built: " + (Join-Path $buildDir "beratools.exe")) -ForegroundColor Green

if (Test-Path $versionInfoPath) {
    Remove-Item $versionInfoPath -Force
}
$resourceSyso = Join-Path $scriptDir "resource.syso"
if (Test-Path $resourceSyso) {
    Remove-Item $resourceSyso -Force
}

# Step 8: Copy application files
Write-Host "`n[8/9] Copying application files..." -ForegroundColor Yellow


# Copy entire beratools package
$srcBeratools = Join-Path $scriptDir "..\beratools"
$srcBeratools = [System.IO.Path]::GetFullPath($srcBeratools)
$dstBeratools = Join-Path $buildDir "beratools"
Copy-Item -Path $srcBeratools -Destination $dstBeratools -Recurse -Force
if (-not (Test-Path (Join-Path $dstBeratools "__init__.py"))) {
    Write-Host "Failed to copy beratools package" -ForegroundColor Red
    exit 1
}

$geoSimplifyBinary = Join-Path $dstBeratools "external\geo_simplify\geo-simplify-win-x64.exe"
if (-not (Test-Path $geoSimplifyBinary)) {
    Write-Host "Missing geo-simplify Windows binary at $geoSimplifyBinary" -ForegroundColor Red
    Write-Host "Ensure beratools/external/geo_simplify/geo-simplify-win-x64.exe is committed." -ForegroundColor Yellow
    exit 1
}

Write-Host ("Application files copied to " + $dstBeratools) -ForegroundColor Green

# Step 9: Build installer with Inno Setup
Write-Host "`n[9/9] Building installer with Inno Setup..." -ForegroundColor Yellow

$innoSetup = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if (-not (Test-Path $innoSetup)) {
    Write-Host "Inno Setup not found at $innoSetup" -ForegroundColor Red
    Write-Host "Please install Inno Setup 6 from: https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    exit 1
}

$distDir = Join-Path $scriptDir "dist"
New-Item -Path $distDir -ItemType Directory -Force | Out-Null
Write-Host "APP_VERSION for installer: $env:APP_VERSION" -ForegroundColor Cyan
& $innoSetup "/Q" "beratools.iss"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== BUILD SUCCESSFUL ===" -ForegroundColor Green
    Write-Host "Installer: $distDir\beratools-installer.exe" -ForegroundColor Green
    Write-Host "`nTo test: $distDir\beratools-installer.exe" -ForegroundColor Cyan
} else {
    Write-Host "`n=== BUILD FAILED ===" -ForegroundColor Red
    exit 1
}
