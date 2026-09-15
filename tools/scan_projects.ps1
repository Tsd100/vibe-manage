param(
    [string]$Root = 'D:\Github',
    [string]$OutputDir = (Join-Path $PSScriptRoot '..\inventory')
)

$ErrorActionPreference = 'SilentlyContinue'
$skipNames = @('.git', 'node_modules', 'dist', 'build', 'target', 'venv', '.venv', '__pycache__', 'vendor')
$manifestNames = @('package.json', 'pyproject.toml', 'requirements.txt', 'Cargo.toml', 'go.mod', 'pom.xml', 'composer.json', 'CMakeLists.txt', 'Makefile')

function Get-RepoPaths {
    param([string]$Base)

    $queue = [System.Collections.Generic.Queue[object]]::new()
    $queue.Enqueue([pscustomobject]@{ Path = (Resolve-Path -LiteralPath $Base).Path; Depth = 0 })
    $repos = [System.Collections.Generic.List[string]]::new()

    while ($queue.Count -gt 0) {
        $item = $queue.Dequeue()
        if (Test-Path -LiteralPath (Join-Path $item.Path '.git')) {
            $repos.Add($item.Path)
            continue
        }
        if ($item.Depth -ge 5) { continue }

        foreach ($directory in Get-ChildItem -LiteralPath $item.Path -Directory -Force) {
            if ($skipNames -notcontains $directory.Name) {
                $queue.Enqueue([pscustomobject]@{ Path = $directory.FullName; Depth = $item.Depth + 1 })
            }
        }
    }

    return $repos | Sort-Object
}

function Get-ReadmeInfo {
    param([string]$RepoPath)

    $readme = Get-ChildItem -LiteralPath $RepoPath -File -Force |
        Where-Object { $_.Name -match '^README(\..*)?$' } |
        Sort-Object @{ Expression = { if ($_.Name -eq 'README.md') { 0 } else { 1 } } }, Name |
        Select-Object -First 1

    if (-not $readme) {
        return [pscustomobject]@{ File = ''; Title = ''; Purpose = '' }
    }

    $lines = @(Get-Content -LiteralPath $readme.FullName -TotalCount 180)
    $title = ''
    $headingIndex = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^#\s+(.+)$') {
            $title = $Matches[1].Trim()
            $headingIndex = $i
            break
        }
    }

    $purposeLines = [System.Collections.Generic.List[string]]::new()
    if ($headingIndex -ge 0) {
        for ($i = $headingIndex + 1; $i -lt $lines.Count; $i++) {
            $line = $lines[$i].Trim()
            if ($line -match '^#{1,6}\s+') { break }
            if ($line -and $line -notmatch '^```' -and $line -notmatch '^!\[' -and $line -notmatch '^\[') {
                $purposeLines.Add($line)
            }
            if ($purposeLines.Count -ge 2) { break }
        }
    }

    $purpose = ($purposeLines -join ' ')
    $purpose = $purpose -replace '\[([^\]]+)\]\([^\)]+\)', '$1'
    $purpose = $purpose -replace '`', ''
    if ($purpose.Length -gt 220) { $purpose = $purpose.Substring(0, 220) + '…' }

    [pscustomobject]@{ File = $readme.Name; Title = $title; Purpose = $purpose }
}

function Get-PurposeFromManifest {
    param([string]$RepoPath)

    $package = Join-Path $RepoPath 'package.json'
    if (Test-Path -LiteralPath $package) {
        try {
            $data = Get-Content -LiteralPath $package -Raw | ConvertFrom-Json
            if ($data.description) { return [string]$data.description }
        } catch { }
    }
    return ''
}

function Get-Stack {
    param([string[]]$Manifests)
    $stack = [System.Collections.Generic.List[string]]::new()
    if ($Manifests -contains 'package.json') { $stack.Add('Node/前端') }
    if ($Manifests -contains 'pyproject.toml' -or $Manifests -contains 'requirements.txt') { $stack.Add('Python') }
    if ($Manifests -contains 'Cargo.toml') { $stack.Add('Rust') }
    if ($Manifests -contains 'go.mod') { $stack.Add('Go') }
    if ($Manifests -contains 'pom.xml') { $stack.Add('Java') }
    if ($Manifests -contains 'CMakeLists.txt' -or $Manifests -contains 'Makefile') { $stack.Add('原生构建') }
    if ($stack.Count -eq 0) { $stack.Add('未识别') }
    return ($stack -join ' / ')
}

function Invoke-Git {
    param([string]$RepoPath, [string[]]$Arguments)
    $value = & git -C $RepoPath @Arguments 2>$null
    if ($null -eq $value) { return '' }
    return (($value | Out-String).Trim())
}

$repoPaths = @(Get-RepoPaths -Base $Root)
$rows = [System.Collections.Generic.List[object]]::new()

foreach ($repoPath in $repoPaths) {
    $relative = $repoPath.Substring((Resolve-Path -LiteralPath $Root).Path.Length).TrimStart('\').Replace('\', '/')
    $files = @(Get-ChildItem -LiteralPath $repoPath -File -Force)
    $manifestList = @($files | Where-Object { $manifestNames -contains $_.Name } | Select-Object -ExpandProperty Name)
    $readme = Get-ReadmeInfo -RepoPath $repoPath
    $manifestPurpose = Get-PurposeFromManifest -RepoPath $repoPath
    $purpose = if ($manifestPurpose) { $manifestPurpose } elseif ($readme.Purpose) { $readme.Purpose } else { '' }
    $branch = Invoke-Git -RepoPath $repoPath -Arguments @('branch', '--show-current')
    if (-not $branch) { $branch = '(detached)' }
    $dirty = @(Invoke-Git -RepoPath $repoPath -Arguments @('status', '--porcelain') -split "`r?`n" | Where-Object { $_ }).Count
    $last = Invoke-Git -RepoPath $repoPath -Arguments @('log', '-1', '--format=%cI|%s')
    $lastParts = $last -split '\|', 2

    $rows.Add([pscustomobject]@{
        path = $relative
        scope = if ($relative -like '_references/*') { '参考仓库' } else { '项目仓库' }
        name = (Split-Path -Leaf $repoPath)
        title = $readme.Title
        purpose_hint = $purpose
        readme = $readme.File
        manifests = ($manifestList -join ', ')
        stack = (Get-Stack -Manifests $manifestList)
        branch = $branch
        dirty_files = $dirty
        head = (Invoke-Git -RepoPath $repoPath -Arguments @('rev-parse', '--short', 'HEAD'))
        last_commit = if ($lastParts.Count -gt 0) { [string]$lastParts[0] } else { [string]'' }
        last_subject = if ($lastParts.Count -gt 1) { [string]$lastParts[1] } else { [string]'' }
        review = if ($purpose) { '自动提取，可复核' } else { '需要人工补充用途' }
    })
}

$rows = @($rows | Sort-Object path)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$jsonPath = Join-Path $OutputDir 'projects-inventory.json'
$markdownPath = Join-Path $OutputDir 'projects-inventory.md'
$rows | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $jsonPath -Encoding utf8

$dirtyCount = @($rows | Where-Object { [int]$_.dirty_files -gt 0 }).Count
$missingPurposeCount = @($rows | Where-Object { $_.review -eq '需要人工补充用途' }).Count
$today = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
$md = [System.Text.StringBuilder]::new()
[void]$md.AppendLine('# D:\Github 项目只读盘点')
[void]$md.AppendLine()
[void]$md.AppendLine(('扫描时间：{0}' -f $today))
[void]$md.AppendLine(('扫描根目录：`{0}`' -f $Root))
[void]$md.AppendLine(('Git 仓库数量：**{0}**（其中项目仓库 **{1}**、参考仓库 **{2}**）；存在未提交修改：**{3}**；用途待补充：**{4}**' -f $rows.Count, @($rows | Where-Object { $_.scope -eq '项目仓库' }).Count, @($rows | Where-Object { $_.scope -eq '参考仓库' }).Count, $dirtyCount, $missingPurposeCount))
[void]$md.AppendLine()
[void]$md.AppendLine('说明：本清单只读取目录、README/工程清单和本地 Git 元数据；`dirty_files` 是 `git status --porcelain` 行数，不代表问题严重程度。')
[void]$md.AppendLine()
[void]$md.AppendLine('| 范围 | 路径 | 用途线索 | 技术栈 | 分支 | 未提交 | 最近提交 | 复核 |')
[void]$md.AppendLine('|---|---|---|---|---|---:|---|---|')
foreach ($row in $rows) {
    $purposeCell = if ($row.purpose_hint) { $row.purpose_hint } elseif ($row.title) { $row.title } else { '待补充' }
    $purposeCell = $purposeCell.Replace('|', '\|').Replace("`r", ' ').Replace("`n", ' ')
    $subject = if ($row.last_subject) { $row.last_subject.Replace('|', '\|') } else { '无提交记录' }
    $lastCommitText = if ($row.last_commit) { [string]$row.last_commit } else { '' }
    $commitDateText = if ($lastCommitText) { $lastCommitText.Substring(0, [Math]::Min(10, $lastCommitText.Length)) } else { '' }
    $commitCell = if ($commitDateText) { '{0} {1}' -f $commitDateText, $subject } else { $subject }
    $rowLine = ('| {0} | `{1}` | {2} | {3} | `{4}` | {5} | {6} | {7} |' -f $row.scope, $row.path, $purposeCell, $row.stack, $row.branch, $row.dirty_files, $commitCell, $row.review)
    [void]$md.AppendLine($rowLine)
}
[void]$md.AppendLine()
[void]$md.AppendLine('## 下一步人工确认队列')
[void]$md.AppendLine()
foreach ($row in ($rows | Where-Object { $_.review -eq '需要人工补充用途' })) {
    [void]$md.AppendLine(('- `{0}`：补充项目用途、当前阶段、下一步动作。' -f $row.path))
}
$md.ToString() | Set-Content -LiteralPath $markdownPath -Encoding utf8

Write-Output ('Scanned {0} repositories.' -f $rows.Count)
Write-Output ('JSON: {0}' -f $jsonPath)
Write-Output ('Markdown: {0}' -f $markdownPath)
