param(
    [switch]$Login,
    [switch]$Check
)

if ($Login -and $Check) {
    [Console]::Error.WriteLine("Use either -Login or -Check, not both.")
    exit 1
}

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$ConfigFile = Join-Path $ProjectRoot "config.conf"

if (-not (Test-Path -LiteralPath $ConfigFile -PathType Leaf)) {
    [Console]::Error.WriteLine("config.conf is missing from the project root.")
    exit 1
}

$config = @{}

try {
    foreach ($configLine in (Get-Content -LiteralPath $ConfigFile -Encoding UTF8)) {
        $line = $configLine.Trim()

        if ($line -eq "" -or $line.StartsWith("#")) {
            continue
        }

        $parts = $line -split "=", 2

        if ($parts.Count -ne 2 -or [string]::IsNullOrWhiteSpace($parts[0])) {
            throw "config.conf must contain KEY=VALUE entries."
        }
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.Length -ge 2 -and (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        )) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($config.ContainsKey($key)) {
            throw "config.conf contains a duplicate key."
        }
        $config[$key] = $value
    }
    foreach ($requiredKey in @("APP_ID", "APP_SECRET")) {
        if (-not $config.ContainsKey($requiredKey)) {
            throw "config.conf is missing $requiredKey."
        }
        if ([string]::IsNullOrWhiteSpace($config[$requiredKey])) {
            throw "config.conf has an empty $requiredKey."
        }
        if ($config[$requiredKey] -match '^(cli_your_app_id|your_app_secret|your_.+|replace_.+|<.+>)$') {
            throw "config.conf still has a placeholder for $requiredKey."
        }
    }
} catch {
    # Never print a raw configuration line or an exception containing its value.
    if ($_.Exception.Message -like "config.conf *") {
        [Console]::Error.WriteLine($_.Exception.Message)
    } else {
        [Console]::Error.WriteLine("Unable to read config.conf.")
    }
    exit 1
}

$CliPath = Join-Path $ProjectRoot "node_modules/@larksuiteoapi/lark-mcp/dist/cli.js"
$EntryPath = Join-Path $PSScriptRoot "lark-runtime.cjs"
if (-not (Test-Path -LiteralPath $EntryPath -PathType Leaf)) {
    [Console]::Error.WriteLine("The project runtime adapter is missing.")
    exit 1
}
$PackagePath = Join-Path $ProjectRoot "node_modules/@larksuiteoapi/lark-mcp/package.json"
if (-not (Test-Path -LiteralPath $CliPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
    [Console]::Error.WriteLine("Local lark-mcp is missing. Run npm ci in the project root.")
    exit 1
}
try {
    $installed = Get-Content -LiteralPath $PackagePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($installed.version -ne "0.5.1") { throw "version mismatch" }
} catch {
    [Console]::Error.WriteLine("Local lark-mcp must be version 0.5.1. Run npm ci in the project root.")
    exit 1
}
$Node = Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Node) {
    [Console]::Error.WriteLine("Node.js 20 or later is required.")
    exit 1
}
$nodeVersion = & $Node.Source --version
if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v(\d+)\.' -or [int]$Matches[1] -lt 20) {
    [Console]::Error.WriteLine("Node.js 20 or later is required.")
    exit 1
}
if ($Check) {
    [Console]::Out.WriteLine("Configuration and local lark-mcp 0.5.1 are ready. OAuth and API access were not checked.")
    exit 0
}

$FeishuTools = @(
    "docx.builtin.search",
    "docx.builtin.import",
    "docx.v1.document.get",
    "docx.v1.document.rawContent",
    "docx.v1.documentBlock.get",
    "docx.v1.documentBlock.list",
    "docx.v1.documentBlock.patch",
    "docx.v1.documentBlockChildren.create",
    "docx.v1.documentBlockChildren.batchDelete",
    "drive.v1.importTask.get",
    "drive.v1.file.delete",
    "wiki.v1.node.search",
    "wiki.v2.space.list",
    "wiki.v2.space.get",
    "wiki.v2.space.create",
    "wiki.v2.space.getNode",
    "wiki.v2.spaceNode.list",
    "wiki.v2.spaceNode.create",
    "wiki.v2.spaceNode.moveDocsToWiki",
    "wiki.v2.spaceNode.move",
    "wiki.v2.spaceNode.updateTitle",
    "wiki.v2.task.get"
) -join ","

# API permissions must also be enabled/published in the developer console and
# granted by the user. A tool whitelist does not grant API or document access.
$FeishuScopes = @(
    "docx:document",
    "drive:drive",
    "wiki:wiki",
    "offline_access"
) -join " "

# Use process-local environment only; never inherit a manually supplied user token.
$SavedEnvironment = @{}
foreach ($name in @("APP_ID", "APP_SECRET", "USER_ACCESS_TOKEN")) {
    $SavedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$ExitCode = 1
try {
    $env:APP_ID = $config["APP_ID"]
    $env:APP_SECRET = $config["APP_SECRET"]
    Remove-Item Env:USER_ACCESS_TOKEN -ErrorAction SilentlyContinue

    # Avoid loading a caller's .env through the upstream CLI's dotenv behavior.
    $WorkingDirectory = Join-Path $ProjectRoot ".runtime/mcp"
    New-Item -ItemType Directory -Path $WorkingDirectory -Force | Out-Null
    Push-Location -LiteralPath $WorkingDirectory
    try {
        [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        $OutputEncoding = [Console]::OutputEncoding
        if ($Login) {
            & $Node.Source $EntryPath login --domain https://open.feishu.cn --scope $FeishuScopes
        } else {
            & $Node.Source $EntryPath mcp --domain https://open.feishu.cn --mode stdio `
                --oauth --token-mode user_access_token --scope $FeishuScopes -t $FeishuTools -l zh
        }
        $ExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} catch {
    # Do not print an exception that might include environment or configuration data.
    [Console]::Error.WriteLine("Unable to run local lark-mcp.")
} finally {
    foreach ($name in $SavedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $SavedEnvironment[$name], "Process")
    }
}
exit $ExitCode
