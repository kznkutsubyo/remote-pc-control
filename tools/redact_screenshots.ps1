param(
    [Parameter(Mandatory=$true)][string]$SourceDirectory,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\artifacts\screenshots-redacted')
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$items = @(
    @('22_39_50_22','remote-light', 'header,account'),
    @('22_39_57_30','studio-light', 'header'),
    @('22_40_01_58','studio-mac-original', 'header,macOriginal'),
    @('22_40_33_23','studio-mac-light', 'header'),
    @('22_40_35_05','studio-mac-dark', 'header'),
    @('22_40_37_56','studio-dark-earlier', 'header'),
    @('22_40_46_29','transfer-dark-earlier', 'header'),
    @('22_41_04_05','settings-dark', ''),
    @('22_42_24_59','signin-validation', 'signinAccount'),
    @('22_53_37_20','signin-status', 'signinDevice'),
    @('23_00_40_45','remote-dark', 'device'),
    @('23_00_44_69','media-dark', 'device,history'),
    @('23_00_47_41','studio-dark', 'device'),
    @('23_00_52_03','studio-mac-masked', 'device'),
    @('23_00_57_32','transfer-dark', 'device'),
    @('22_39_43_51','remote-dark-earlier', 'header,account')
)
$regions = @{
    device = @(0.140,0.079,0.470,0.105)
    address = @(0.320,0.113,0.580,0.136)
    account = @(0.220,0.514,0.900,0.548)
    macOriginal = @(0.130,0.628,0.860,0.673)
    signinAccount = @(0.250,0.109,0.940,0.165)
    signinDevice = @(0.250,0.109,0.780,0.147)
    history = @(0.800,0.706,0.914,0.870)
}
foreach ($item in $items) {
    $matches = @(Get-ChildItem -LiteralPath $SourceDirectory -Filter ('Screenshot_2026_11_07_'+$item[0]+'_*.jpg') -File)
    if ($matches.Count -ne 1) { throw "Expected one source screenshot for $($item[1])" }
    $source = [Drawing.Image]::FromFile($matches[0].FullName)
    $bitmap = New-Object Drawing.Bitmap($source.Width,$source.Height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.DrawImageUnscaled($source,0,0)
        $brush = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(255,51,54,63))
        $ink = New-Object Drawing.SolidBrush([Drawing.Color]::White)
        $font = New-Object Drawing.Font('Segoe UI',([float]($bitmap.Width*0.020)),[Drawing.FontStyle]::Bold,[Drawing.GraphicsUnit]::Pixel)
        $format = New-Object Drawing.StringFormat
        $format.Alignment = [Drawing.StringAlignment]::Center
        $format.LineAlignment = [Drawing.StringAlignment]::Center
        $masks = @($item[2].Split(',') | Where-Object {$_})
        if ($masks -contains 'header') { $masks = @($masks | Where-Object {$_ -ne 'header'}) + @('device','address') }
        # Remove the status bar as well: timestamps and phone/network state are unnecessary for a gallery.
        $graphics.FillRectangle($brush,0,0,$bitmap.Width,[int]($bitmap.Height*0.05))
        foreach ($key in $masks) {
            $r=$regions[$key]
            $rect=New-Object Drawing.RectangleF([float]($r[0]*$bitmap.Width),[float]($r[1]*$bitmap.Height),[float](($r[2]-$r[0])*$bitmap.Width),[float](($r[3]-$r[1])*$bitmap.Height))
            $graphics.FillRectangle($brush,$rect)
            $graphics.DrawString('HIDDEN',$font,$ink,$rect,$format)
        }
        $destination=Join-Path $OutputDirectory ($item[1]+'.png')
        $cut=[int]($bitmap.Height*0.05)
        $cropped=$bitmap.Clone((New-Object Drawing.Rectangle(0,$cut,$bitmap.Width,($bitmap.Height-$cut))),[Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try { $cropped.Save($destination,[Drawing.Imaging.ImageFormat]::Png) } finally { $cropped.Dispose() }
        Write-Output $destination
        $brush.Dispose();$ink.Dispose();$font.Dispose();$format.Dispose()
    } finally { $graphics.Dispose();$bitmap.Dispose();$source.Dispose() }
}
