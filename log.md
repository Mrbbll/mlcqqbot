Get-ChildItem -LiteralPath 'D:\desktop\bot\mlcqqbot' -Directory -Filter '__pycache__' -Recurse -Force |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }