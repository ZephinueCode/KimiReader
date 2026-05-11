# KimiReader Install Script for Windows
# Requires: PowerShell 5.1+ or PowerShell Core
# Run as: .\install-windows.ps1

$ErrorActionPreference = "Stop"

$PluginName = "kimireader"
$PluginVersion = "2.0.0"

function Write-Header($text) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host $text -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
}

function Write-Success($text) {
    Write-Host "[OK] $text" -ForegroundColor Green
}

function Write-Warning($text) {
    Write-Host "[WARN] $text" -ForegroundColor Yellow
}

function Write-Error($text) {
    Write-Host "[ERR] $text" -ForegroundColor Red
}

# ==================== 0. Detect Project Root ====================
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

Write-Header "KimiReader Installer for Windows"
Write-Host "Project root: $ProjectRoot"

# ==================== 1. Check Python ====================
Write-Header "Step 1: Checking Python"

$PythonCmd = $null
$PythonCandidates = @("python", "python3", "py")

foreach ($cmd in $PythonCandidates) {
    $exe = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($exe) {
        try {
            $verStr = & $cmd --version 2>&1
            if ($verStr -match "Python\s+(\d+)\.(\d+)") {
                $major = [int]$matches[1]
                $minor = [int]$matches[2]
                if ($major -ge 3 -and $minor -ge 8) {
                    $PythonCmd = $cmd
                    Write-Success "Found Python $verStr at $($exe.Source)"
                    break
                } else {
                    Write-Warning "Found $cmd but version too old: $verStr (need 3.8+)"
                }
            }
        } catch {
            continue
        }
    }
}

if (-not $PythonCmd) {
    Write-Error "Python 3.8+ not found. Please install Python from https://python.org"
    exit 1
}

# ==================== 2. Install Dependencies ====================
Write-Header "Step 2: Installing Python Dependencies"

$RequirementsFile = Join-Path $ProjectRoot "browser_agent\requirements.txt"
if (Test-Path $RequirementsFile) {
    & $PythonCmd -m pip install -r $RequirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install requirements"
        exit 1
    }
    Write-Success "Python packages installed"
} else {
    Write-Warning "requirements.txt not found, installing playwright directly"
    & $PythonCmd -m pip install playwright
}

# ==================== 3. Install Playwright Browsers ====================
Write-Header "Step 3: Installing Playwright Browsers"

& $PythonCmd -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Warning "playwright install chromium failed, trying with deps..."
    & $PythonCmd -m playwright install --with-deps chromium
}
Write-Success "Playwright Chromium browser installed"

# ==================== 4. Install CLI Plugin ====================
Write-Header "Step 4: Installing Kimi Code CLI Plugin"

$KimiPluginsDir = Join-Path $env:USERPROFILE ".kimi\plugins"
$PluginTargetDir = Join-Path $KimiPluginsDir $PluginName

if (-not (Test-Path $KimiPluginsDir)) {
    New-Item -ItemType Directory -Path $KimiPluginsDir -Force | Out-Null
}

# Remove old version if exists
if (Test-Path $PluginTargetDir) {
    Write-Warning "Removing old plugin at $PluginTargetDir"
    Remove-Item -Recurse -Force $PluginTargetDir
}

# Step 4a: Copy plugin static config (plugin.json, config.json)
$PluginSourceDir = Join-Path $ProjectRoot "plugin"
Copy-Item -Recurse -Path $PluginSourceDir -Destination $PluginTargetDir
Write-Success "Plugin static files installed"

# Step 4b: Copy browser_agent code from project root (source of truth)
# This ensures we always install the latest code, not stale copies in plugin/scripts/
$BrowserAgentSource = Join-Path $ProjectRoot "browser_agent"
$BrowserAgentTarget = Join-Path $PluginTargetDir "scripts\browser_agent"
if (Test-Path $BrowserAgentTarget) {
    Remove-Item -Recurse -Force $BrowserAgentTarget
}
Copy-Item -Recurse -Path $BrowserAgentSource -Destination $BrowserAgentTarget
Write-Success "Browser agent code synced from $BrowserAgentSource"

# ==================== 5. Install User-Level Skill ====================
Write-Header "Step 5: Installing Agent Skill"

$UserSkillsDir = Join-Path $env:USERPROFILE ".config\agents\skills"
$KimiSkillsDir = Join-Path $env:USERPROFILE ".kimi\skills"

# Try .kimi/skills first (brand-specific, higher priority)
$SkillTargetDir = $KimiSkillsDir
if (-not (Test-Path $KimiSkillsDir)) {
    New-Item -ItemType Directory -Path $KimiSkillsDir -Force | Out-Null
}

# Install chat-to-code skill
$SkillSource = Join-Path $ProjectRoot "skill\chat-to-code"
$SkillDest = Join-Path $SkillTargetDir "chat-to-code"
if (Test-Path $SkillDest) { Remove-Item -Recurse -Force $SkillDest }
Copy-Item -Recurse -Path $SkillSource -Destination $SkillDest
Write-Success "Skill 'chat-to-code' installed to $SkillDest"

# Install 导入聊天记录 skill
$ImportSkillSource = Join-Path $ProjectRoot "skill\import-chat"
$ImportSkillDest = Join-Path $SkillTargetDir "import-chat"
if (Test-Path $ImportSkillDest) { Remove-Item -Recurse -Force $ImportSkillDest }
Copy-Item -Recurse -Path $ImportSkillSource -Destination $ImportSkillDest
Write-Success "Skill '导入聊天记录' installed to $ImportSkillDest"

# ==================== 6. VSCode Extension Check ====================
Write-Header "Step 6: VSCode Extension Check"

$VSCodeExtDir = Join-Path $env:USERPROFILE ".vscode\extensions"
$KimiVSCodeExt = Get-ChildItem -Path $VSCodeExtDir -Filter "moonshot-ai.kimi-code-*" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($KimiVSCodeExt) {
    Write-Success "Found VSCode Kimi Code extension: $($KimiVSCodeExt.Name)"
    Write-Host "Note: VSCode Kimi Code uses the same CLI underneath, so the plugin should work in VSCode too."
    Write-Host "To use in VSCode: open Kimi Code chat panel, then type '/flow:chat-to-code' or '/skill:chat-to-code-plan'"
} else {
    Write-Warning "VSCode Kimi Code extension not found. You can install it from VSCode marketplace."
}

# ==================== 7. Project-Level Skill (Optional) ====================
Write-Header "Step 7: Project-Level Skill (Optional)"

$GitRoot = $null
try {
    $GitRoot = & git rev-parse --show-toplevel 2>$null
} catch {}

if ($GitRoot) {
    $ProjectSkillDir = Join-Path $GitRoot ".kimi\skills\chat-to-code"
    $ProjectImportSkillDir = Join-Path $GitRoot ".kimi\skills\导入聊天记录"
    if (-not (Test-Path $ProjectSkillDir)) {
        $response = Read-Host "Install Skills to current project ($GitRoot)? [Y/n]"
        if ($response -eq "" -or $response -match "^[Yy]") {
            New-Item -ItemType Directory -Path (Split-Path $ProjectSkillDir) -Force | Out-Null
            Copy-Item -Recurse -Path $SkillSource -Destination $ProjectSkillDir
            $ProjectImportSkillDir = Join-Path $GitRoot ".kimi\skills\import-chat"
            Copy-Item -Recurse -Path $ImportSkillSource -Destination $ProjectImportSkillDir
            Write-Success "Project-level skills installed"
        }
    }
} else {
    Write-Warning "Not in a git repository. Project-level skill not installed."
    Write-Host "You can manually copy 'skill/chat-to-code' to your project's '.kimi/skills/' directory."
}

# ==================== 8. Fix python3 command in plugin.json for Windows ====================
Write-Header "Step 8: Adapting Plugin for Windows Python"

# On Windows, "python3" may not work. Try to use the detected command.
# We will create a wrapper in the plugin directory.
$PythonExe = (Get-Command $PythonCmd).Source
Write-Host "Detected Python executable: $PythonExe"

# Create a python3.cmd wrapper in plugin directory
$WrapperPath = Join-Path $PluginTargetDir "python3.cmd"
$WrapperContent = @"
@echo off
"$PythonExe" %*
"@
Set-Content -Path $WrapperPath -Value $WrapperContent
Write-Success "Created python3.cmd wrapper at $WrapperPath"

# ==================== 9. Final Instructions ====================
Write-Header "Installation Complete!"

Write-Host "`nNext steps:"
Write-Host "1. Restart Kimi Code CLI (or VSCode if using the extension)"
Write-Host "2. Run the following command in Kimi Code chat:"
Write-Host "   /flow:chat-to-code"
Write-Host "   or"
Write-Host "   /skill:chat-to-code-plan"
Write-Host "`n3. First time only: you may need to login:"
Write-Host "   The Flow will prompt you to login if not already logged in."
Write-Host "   Or manually run:"
Write-Host "   -> kimi_login (opens browser for manual login)"
Write-Host "`n4. Your login state is saved at:"
Write-Host "   $($env:USERPROFILE)\.kimireader"
Write-Host "`nFor help, see README.md in $ProjectRoot"
