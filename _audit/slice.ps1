param(
    [string]$File = "main.py",
    [int]$Start = 1,
    [int]$End = 100
)
$lines = Get-Content -LiteralPath $File
for ($i = $Start; $i -le $End -and $i -le $lines.Count; $i++) {
    "{0}: {1}" -f $i, $lines[$i - 1]
}
