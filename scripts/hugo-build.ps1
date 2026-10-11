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
    stdout 的完成标记（`Total in … ms`），出现后即回收整棵进程树并以 0 退出 ——
    此时产物一定是完整的。

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

# 关键的一行：降并发，避开 Windows 上的并行渲染竞争
$env:HUGO_NUMWORKERMULTIPLIER = '1'

if (-not $HugoArgs -or $HugoArgs.Count -eq 0) { $HugoArgs = @('--gc', '--minify') }

# server 模式：它就该一直跑着，没有「退不出」的问题，直接转交
if ($HugoArgs -contains 'server') {
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

        # 「Total in … ms」是 Hugo 统计表的最后一行，出现即代表构建真正完成
        if (Test-Path $outFile) {
            try {
                if (Select-String -LiteralPath $outFile -Pattern 'Total in \d+ ms' -Quiet -ErrorAction Stop) {
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

    Start-Sleep -Milliseconds 150
    Write-NewLines -Path $outFile -Printed ([ref]$outN)
    Write-NewLines -Path $errFile -Printed ([ref]$errN) -Color 'Red'

    if ($completed -and -not $proc.HasExited) {
        Stop-Tree $proc.Id
        Write-Host ""
        Write-Host "构建已完成，但 hugo 进程没退出（Dart Sass 握手失败留下的子进程），已回收。" -ForegroundColor Yellow
        Write-Host "产物是完整的，可以直接用。" -ForegroundColor DarkGray
        exit 0
    }

    if ($completed) { exit 0 }
    exit $proc.ExitCode
}
finally {
    Remove-Item $outFile, $errFile -Force -ErrorAction SilentlyContinue
    if (-not $proc.HasExited) { Stop-Tree $proc.Id }
}
