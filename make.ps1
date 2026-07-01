<#
.SYNOPSIS
    该脚本用于打包 "Seraphine" 。

.PARAMETER dest
    输出的目标路径。默认为当前目录。

.PARAMETER dbg
    是否启用调试模式。如果启用，将不会删除 `.\dist` 目录，也不会创建 ZIP 文件。

.EXAMPLE
    .\make.ps1 -dbg
#>

# 输出格式：ZIP（使用 PowerShell 内置 Compress-Archive，无需安装 7-Zip）

param(
    [Parameter()]
    [String]$dest = ".",
    [Switch]$dbg
)

$ErrorActionPreference = "Stop"

if (Test-Path .\dist) {
    rm -r -Force .\dist
}

pyinstaller -w -i .\app\resource\images\logo.ico --hidden-import backports.zstd --collect-all pyzstd --collect-all backports.zstd main.py
Start-Sleep -Seconds 2
rm -r -fo .\build
rm -r -fo .\main.spec
Copy-Item -Path ".\dist\main" -Destination ".\dist\Seraphine" -Recurse -Force
Remove-Item -Path ".\dist\main" -Recurse -Force
Rename-Item -Path ".\dist\Seraphine\main.exe" -NewName "Seraphine.exe"
cpi .\app -destination .\dist\Seraphine -recurse
rm -r .\dist\Seraphine\app\common
rm -r .\dist\Seraphine\app\components
rm -r .\dist\Seraphine\app\lol
rm -Path .\dist\Seraphine\app\resource\game* -r
rm -r .\dist\Seraphine\app\resource\i18n\Seraphine.zh_CN.ts
rm -r .\dist\Seraphine\app\resource\bin\fix_lcu_window.c
rm -r .\dist\Seraphine\app\resource\bin\readme.md
rm -r .\dist\Seraphine\app\view

$files = Get-ChildItem -Path ".\dist\Seraphine\*" -Recurse |
    Select-Object -ExpandProperty FullName |
    ForEach-Object { $_.Replace((Resolve-Path ".\dist\Seraphine").Path + "\", "") }

$files | Out-File -FilePath ".\dist\Seraphine\filelist.txt" -Encoding UTF8

if (! $dbg) {
    Compress-Archive -Path ".\dist\Seraphine\*" -DestinationPath "$dest\Seraphine.zip" -Force
    rm -r .\dist
}
