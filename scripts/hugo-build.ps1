<#
.SYNOPSIS
    Windows 上跑 Hugo 构建：修掉「经常卡很久」的问题，并保证不会卡死。

.DESCRIPTION
    ── 问题（2026-10-11 实测，Hugo v0.167.0 extended / Windows 11）──

    直接用 `hugo --gc --minify` 在本机大约有三到六成的概率会「卡很久」，表现是
    终端停在 `Start building sites …` 不动，或者跑完统计表之后再也不返回。

    ── 根因 ──

    不是 Sass 慢，而是 Hugo 的**并行渲染在 Windows 上存在竞争**：

    1. 主题要编译多个 SCSS 入口（main / custom / 分页 CSS / aplayer / valine …），
       并发渲染时 Hugo 会同时和多个 Dart Sass 子进程走 embedded 协议，握手会打架。
       握手失败的代价是干等 **30 秒**（Hugo 的内部超时），超时后它自己恢复并重新
       编译成功 —— 所以**产物从来没错过**，即使把 resources/ 和 public/ 全删掉，
       卡住那次产出的 CSS 也与健康构建逐字节一致。
    2. 但那个握手失败的 sass 进程不会被回收，Hugo 退出时要等它，于是永远停住。
       所以「卡很久」的时候，站点其实早就编译好了。
    3. 同一个竞争还会漏解析正文里的相对链接。本机实测同一份源码：
         并发构建 → <a href=mpv.conf>
         降并发后 → <a href=/my-mpv-config/mpv.conf>   （正确解析成永久链接）

    ── 已排除的原因（都实测过）──

    * 不是 `cmd.exe` 中转：自建原生 sass.exe 转发器后卡顿率只从 40% 降到 30%。
    * 不是残留进程：清空后再跑，复现率不变。
    * 不是缓存回退：删掉 resources/ 与 public/ 后产出依然完整正确。
    * 不是 Dart VM 启动慢/被杀软扫描：30 次启动耗时全在 0.02–0.05 秒。
    * 不是构建节奏：背靠背与间隔 8 秒复现率一样。
    * 不是版本回归：0.166.0 卡得比 0.167.0 还多。

    ── 解法 ──

    `HUGO_NUMWORKERMULTIPLIER=1`（Hugo 官方环境变量，控制并行处理的 worker 数，
    默认取逻辑 CPU 数）把并发降下来，竞争就没了。本机实测 25 次连续构建：
    **25/25 完成、0 次停顿、退出码全 0**，代价是单次构建从约 1.4 秒变成约 2.2 秒。
    这份脚本替你设好这个变量。

    另外保留一层保险：万一还是遇到那种「构建已完成但进程不退」的情况，脚本会盯着
    stdout 的完整耗时行（`Total in … ms`），先最多 2 秒补读日志，再等最多
    `HUGO_BUILD_EXIT_GRACE_SEC` 秒（默认 5）让进程正常退出；仍不退才回收整棵进程树。
    回收后（或进程正常退出后）会做本次产物守卫：目标目录里 index.html 非空且本次写入、
    至少两个 HTML 本次更新、日志里没有 ERROR。
    注意：`Total` 只是耗时行，守卫通过也不等于“完整性证明”；成功判定见验证总纲。

.NOTES
    参数全部原样透传给 hugo，不传则默认 `--gc --minify`（与 CI 一致）。
    含 `server` 时直接转交 —— server 本来就该一直跑，没有「退不出」的问题。

    这里刻意不写 param() 块：写了之后 `-D` / `--logLevel` 这种带横杠的参数会被
    PowerShell 当成脚本自己的参数名去绑定，报「无法将 --logLevel 转换为 Int32」。
    不声明参数块时全部参数进 $args，可以原样转发。

    单次构建的硬上限默认 300 秒（正常约 2 秒），可用环境变量
    HUGO_BUILD_TIMEOUT 调整。

.EXAMPLE
    .\scripts\hugo-build.ps1
    .\scripts\hugo-build.ps1 -D --gc --logLevel warn   # 参数原样透传
    .\scripts\hugo-build.ps1 server -D                 # 开发服务器
#>

$ErrorActionPreference = 'Stop'

$HugoArgs  = $args
$TimeoutSec = if ($env:HUGO_BUILD_TIMEOUT) { [int]$env:HUGO_BUILD_TIMEOUT } else { 300 }
# Total 出现后给进程的正常收尾宽限（秒，默认 5）；慢机器可调大
$ExitGraceMs = if ($env:HUGO_BUILD_EXIT_GRACE_SEC) {
    [int]([double]$env:HUGO_BUILD_EXIT_GRACE_SEC * 1000)
} else { 5000 }

# 关键的一行：降并发，避开 Windows 上的并行渲染竞争
$env:HUGO_NUMWORKERMULTIPLIER = '1'

if (-not $HugoArgs -or $HugoArgs.Count -eq 0) { $HugoArgs = @('--gc', '--minify') }

# 解析真正的子命令，跳过带值选项及其值（--destination new 里的 new 不是命令）
function Get-HugoCommand {
    param([string[]]$HugoArgsIn)
    # 依据 Hugo 0.169.0 的全局 flags 校准；布尔开关不要放进来
    $valueOpts = @(
        '-b', '--baseURL', '-c', '--contentDir', '-d', '--destination',
        '-e', '--environment', '-l', '--layoutDir', '-s', '--source',
        '-t', '--theme', '--cacheDir', '--clock', '--config', '--configDir',
        '--disableKinds', '--ignoreVendorPaths', '--logLevel', '--poll',
        '--renderSegments', '--themesDir', '--trace'
    )
    for ($i = 0; $i -lt $HugoArgsIn.Count; $i++) {
        $a = $HugoArgsIn[$i]
        if ($a -ceq '--') { break }
        if ($a -clike '--*=*' -or $a -clike '-?=*') { continue }
        if ($valueOpts -ccontains $a) { $i++; continue }
        if ($a -clike '-*') { continue }
        return $a
    }
    return ''
}

function Test-IsBuildCall {
    param([string[]]$HugoArgsIn)
    # --help / -h 出现在命令后（如 `build --help`）也不要产物守卫
    foreach ($a in $HugoArgsIn) {
        if ($a -ceq '--help' -or $a -ceq '-h') { return $false }
    }
    $cmd = Get-HugoCommand -HugoArgsIn $HugoArgsIn
    if ($cmd -ceq '') { return $true }
    $nonBuild = @('version', 'env', 'config', 'list', 'new', 'mod',
                  'completion', 'gen', 'convert', 'import', 'help')
    return -not ($nonBuild -ccontains $cmd)
}

# server 模式：它就该一直跑着，没有「退不出」的问题，直接转交
if ((Get-HugoCommand -HugoArgsIn $HugoArgs) -ceq 'server') {
    & hugo @HugoArgs
    exit $LASTEXITCODE
}

$stamp   = [guid]::NewGuid().ToString('N')
$outFile = Join-Path $env:TEMP "hugo-build-$stamp.out"
$errFile = Join-Path $env:TEMP "hugo-build-$stamp.err"

function Write-NewLines {
    param([string]$Path, [ref]$Printed, [string]$Color)
    if (-not (Test-Path $Path)) { return }
    try { $lines = @(Get-Content -LiteralPath $Path -ErrorAction Stop) } catch { return }
    if ($lines.Count -le $Printed.Value) { return }
    $new = $lines[$Printed.Value..($lines.Count - 1)]
    $Printed.Value = $lines.Count
    foreach ($l in $new) {
        if ($Color) { Write-Host $l -ForegroundColor $Color } else { Write-Host $l }
    }
}

function Stop-Tree {
    param([int]$Id)
    # /T 连同子进程一起收：hugo 底下挂着 cmd.exe → dart.exe（Dart Sass）
    & taskkill /PID $Id /T /F 2>&1 | Out-Null
}

function Get-HugoDestination {
    param([string[]]$HugoArgsIn)
    $dest = 'public'
    for ($i = 0; $i -lt $HugoArgsIn.Count; $i++) {
        $a = $HugoArgsIn[$i]
        # -ceq / -clike 区分大小写：-D（--buildDrafts）不是 -d（--destination）
        if ($a -ceq '-d' -or $a -ceq '--destination') {
            if ($i + 1 -lt $HugoArgsIn.Count) { $dest = $HugoArgsIn[$i + 1] }
        }
        elseif ($a -clike '--destination=*') { $dest = $a.Substring('--destination='.Length) }
        elseif ($a -clike '-d=*') { $dest = $a.Substring(3) }
    }
    return $dest
}

function Resolve-PathFromCwd {
    param([string]$Path)
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}

function Test-BuildOutput {
    param(
        [string]$DestDir,
        [string]$IndexPath,
        [datetime]$BuildStart,
        $BeforeMtime,
        $BeforeHash,
        [hashtable]$BeforeHtml
    )
    if (-not (Test-Path -LiteralPath $IndexPath)) { return "缺少 index.html（$IndexPath）" }
    $idx = Get-Item -LiteralPath $IndexPath
    if ($idx.Length -le 0) { return "index.html 是空文件（$IndexPath）" }

    $afterHash = (Get-FileHash -LiteralPath $IndexPath -Algorithm SHA256).Hash
    $mtimeChanged = ($null -eq $BeforeMtime) -or ($idx.LastWriteTimeUtc -ne $BeforeMtime)
    $hashChanged = ($null -eq $BeforeHash) -or ($afterHash -ne $BeforeHash)
    $fresh = $idx.LastWriteTimeUtc -ge $BuildStart.ToUniversalTime()
    if (-not ($mtimeChanged -and ($hashChanged -or $fresh))) {
        return "index.html 不是本次写入（mtime 未变，内容也未变）"
    }

    $startUtc = $BuildStart.ToUniversalTime()
    $newHtml = @(Get-ChildItem -LiteralPath $DestDir -Recurse -Filter *.html -ErrorAction SilentlyContinue |
        Where-Object {
            $prev = $BeforeHtml[$_.FullName]
            ($_.LastWriteTimeUtc -ge $startUtc) -and (($null -eq $prev) -or ($_.LastWriteTimeUtc -ne $prev))
        })
    if ($newHtml.Count -le 1) { return "本次只更新了 $($newHtml.Count) 个 HTML，产物不完整" }
    return $null
}

function Find-BuildError {
    param([string]$OutFile, [string]$ErrFile)
    foreach ($f in @($OutFile, $ErrFile)) {
        if (-not (Test-Path -LiteralPath $f)) { continue }
        try {
            if (Select-String -LiteralPath $f -Pattern '^\s*ERROR\b' -Quiet -ErrorAction Stop) {
                return "日志里有 ERROR：$f"
            }
        } catch { }
    }
    return $null
}

$isBuild = Test-IsBuildCall -HugoArgsIn $HugoArgs

$DestDir = $null
$IndexPath = $null
$BeforeMtime = $null
$BeforeHash = $null
$BeforeHtml = @{}

if ($isBuild) {
    $DestArg = Get-HugoDestination -HugoArgsIn $HugoArgs
    $DestDir = Resolve-PathFromCwd $DestArg
    $IndexPath = Join-Path $DestDir 'index.html'

    if (Test-Path -LiteralPath $IndexPath) {
        $before = Get-Item -LiteralPath $IndexPath
        $BeforeMtime = $before.LastWriteTimeUtc
        $BeforeHash = (Get-FileHash -LiteralPath $IndexPath -Algorithm SHA256).Hash
    }
    if (Test-Path -LiteralPath $DestDir) {
        Get-ChildItem -LiteralPath $DestDir -Recurse -Filter *.html -ErrorAction SilentlyContinue |
            ForEach-Object { $BeforeHtml[$_.FullName] = $_.LastWriteTimeUtc }
    }
}

$BuildStart = Get-Date
$proc = Start-Process -FilePath 'hugo' -ArgumentList $HugoArgs -NoNewWindow -PassThru `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile

$sw        = [Diagnostics.Stopwatch]::StartNew()
$outN      = 0
$errN      = 0
$completed = $false

try {
    while ($true) {
        Start-Sleep -Milliseconds 120
        Write-NewLines -Path $outFile -Printed ([ref]$outN)
        Write-NewLines -Path $errFile -Printed ([ref]$errN) -Color 'Red'

        # 「Total in … ms」只是耗时行，不能单独证明构建成功；
        # 这里只把它当作“可以开始回收不退出的进程”的信号。
        if (Test-Path $outFile) {
            try {
                if (Select-String -LiteralPath $outFile -Pattern '^\s*Total in \d+ ms' -Quiet -ErrorAction Stop) {
                    $completed = $true
                    break
                }
            } catch { }
        }

        if ($proc.HasExited) { break }

        if ($sw.Elapsed.TotalSeconds -gt $TimeoutSec) {
            Stop-Tree $proc.Id
            Write-Host ""
            Write-Host "hugo 超过 $TimeoutSec 秒仍未完成，已终止。" -ForegroundColor Red
            exit 1
        }
    }

    # 收尾最多读 2 秒，避免为了等重定向输出无限挂住
    $drainUntil = (Get-Date).AddSeconds(2)
    while ((Get-Date) -lt $drainUntil) {
        Write-NewLines -Path $outFile -Printed ([ref]$outN)
        Write-NewLines -Path $errFile -Printed ([ref]$errN) -Color 'Red'
        if ($proc.HasExited) { break }
        Start-Sleep -Milliseconds 120
    }
    Write-NewLines -Path $outFile -Printed ([ref]$outN)
    Write-NewLines -Path $errFile -Printed ([ref]$errN) -Color 'Red'

    # 给正常收尾一个有限宽限；仍不退出才回收
    $exited = $proc.HasExited
    if (-not $exited) {
        $null = $proc.WaitForExit($ExitGraceMs)
        $exited = $proc.HasExited
    }
    $exitCode = if ($exited) { $proc.ExitCode } else { $null }
    $reaped = $false
    if (-not $exited) {
        Stop-Tree $proc.Id
        $reaped = $true
    }

    # 等待/回收期间可能还有几行日志，再读最多 500ms
    for ($i = 0; $i -lt 5; $i++) {
        Write-NewLines -Path $outFile -Printed ([ref]$outN)
        Write-NewLines -Path $errFile -Printed ([ref]$errN) -Color 'Red'
        if ($exited) { break }
        Start-Sleep -Milliseconds 100
    }

    $reason = $null
    if ($isBuild) {
        $reason = Test-BuildOutput -DestDir $DestDir -IndexPath $IndexPath `
            -BuildStart $BuildStart -BeforeMtime $BeforeMtime `
            -BeforeHash $BeforeHash -BeforeHtml $BeforeHtml
        if (-not $reason) { $reason = Find-BuildError -OutFile $outFile -ErrFile $errFile }
    }

    if ($exited -and $exitCode -ne 0) {
        Write-Host ""
        Write-Host "hugo 退出码 $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    if ($reason) {
        Write-Host ""
        Write-Host "构建未通过校验：$reason" -ForegroundColor Red
        Write-Host "如果目标目录里是旧产物，先删掉目标目录再试。" -ForegroundColor DarkGray
        exit 1
    }

    if ($reaped) {
        Write-Host ""
        Write-Host "构建已完成，但 hugo 进程没退出（Dart Sass 握手失败留下的子进程），已回收。" -ForegroundColor Yellow
        Write-Host "本次产物校验通过。" -ForegroundColor DarkGray
    }

    exit 0
}
finally {
    Remove-Item $outFile, $errFile -Force -ErrorAction SilentlyContinue
    if (-not $proc.HasExited) { Stop-Tree $proc.Id }
}
