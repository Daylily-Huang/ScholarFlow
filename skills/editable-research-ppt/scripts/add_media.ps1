param(
 [Parameter(Mandatory=$true)][string]$Source,
 [Parameter(Mandatory=$true)][string]$Config,
 [Parameter(Mandatory=$true)][string]$Output
)
# Optional Windows/desktop-PowerPoint post-processing. No network or macros.
$ErrorActionPreference='Stop'
$src=(Resolve-Path -LiteralPath $Source).Path
$cfgPath=(Resolve-Path -LiteralPath $Config).Path
$dst=[IO.Path]::GetFullPath($Output)
if([IO.Path]::GetExtension($src) -ne '.pptx'){throw 'Source must be a .pptx presentation'}
if($src -eq $dst -or (Test-Path -LiteralPath $dst)){throw 'Use a new output path; source/previous output will not be overwritten.'}
if([IO.Path]::GetExtension($dst) -ne '.pptx'){throw 'Output must be .pptx'}
$cfg=Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$base=Split-Path -Parent $cfgPath
$steps=@($cfg.steps | Where-Object {$null -ne $_});$videos=@($cfg.videos | Where-Object {$null -ne $_})
if($steps.Count+$videos.Count -eq 0){throw 'At least one step or video is required'}
foreach($step in $steps){
 if(($step.slide -isnot [int] -and $step.slide -isnot [long]) -or $step.slide -lt 1 -or @($step.shapes).Count -lt 1){throw 'Step needs integer slide and nonempty shapes array'}
 if([string]::IsNullOrWhiteSpace($step.name)){throw 'Step name required'}
 foreach($name in $step.shapes){if($name -isnot [string] -or [string]::IsNullOrWhiteSpace($name)){throw 'Shape names must be strings'}}
 if($null -eq $step.duration){$step | Add-Member -NotePropertyName duration -NotePropertyValue 0.65}
 $duration=[double]$step.duration
 if([double]::IsNaN($duration) -or [double]::IsInfinity($duration) -or $duration -lt 0.1 -or $duration -gt 10){throw 'Duration must be 0.1..10 seconds'}
}
foreach($video in $videos){
 if(($video.slide -isnot [int] -and $video.slide -isnot [long]) -or $video.slide -lt 1 -or @($video.box).Count -ne 4 -or [string]::IsNullOrWhiteSpace($video.name)){throw 'Video needs integer slide, name and four-number box'}
 if($video.autoplay -isnot [bool] -or $video.loop -isnot [bool]){throw 'Video autoplay and loop must be booleans'}
 if([string]::IsNullOrWhiteSpace($video.path) -or [IO.Path]::IsPathRooted($video.path)){throw 'Video path must be relative to config'}
 $mediaPath=(Resolve-Path -LiteralPath (Join-Path $base $video.path)).Path
 if(-not $mediaPath.StartsWith($base+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Video path escapes config directory'}
 if([IO.Path]::GetExtension($mediaPath) -ne '.mp4'){throw 'Use an MP4 file and test its codec playback'}
 $video | Add-Member -NotePropertyName resolvedPath -NotePropertyValue $mediaPath
}
$app=$null;$pres=$null;$initial=0
try {
 $app=New-Object -ComObject PowerPoint.Application
 $initial=$app.Presentations.Count
 # Untitled opens an independent copy, including when the user has Source open.
 $pres=$app.Presentations.Open($src,0,-1,0)
 # Preflight all slide/shape selectors before modifying the in-memory copy.
 foreach($step in $steps){
  if($step.slide -gt $pres.Slides.Count){throw 'Step slide out of range'}
  $slide=$pres.Slides.Item([int]$step.slide)
  if($slide.TimeLine.MainSequence.Count -gt 0 -or $slide.TimeLine.InteractiveSequences.Count -gt 0){throw 'Step target already has animation; preserve its timeline explicitly instead'}
  foreach($name in $step.shapes){$null=$slide.Shapes.Item([string]$name)}
 }
 foreach($video in $videos){
  if($video.slide -gt $pres.Slides.Count){throw 'Video slide out of range'}
  $b=@($video.box | ForEach-Object {[double]$_})
  foreach($n in $b){if([double]::IsNaN($n) -or [double]::IsInfinity($n)){throw 'Box values must be finite'}}
  if($b[0] -lt 0 -or $b[1] -lt 0 -or $b[2] -le 0 -or $b[3] -le 0 -or $b[0]+$b[2] -gt $pres.PageSetup.SlideWidth -or $b[1]+$b[3] -gt $pres.PageSetup.SlideHeight){throw 'Video box exceeds slide bounds (coordinates are points)'}
 }
 foreach($step in $steps){
  $slide=$pres.Slides.Item([int]$step.slide)
  if(@($step.shapes).Count -eq 1){$shape=$slide.Shapes.Item([string]$step.shapes[0])}
  else{$shape=$slide.Shapes.Range([object[]]@($step.shapes)).Group()}
  $shape.Name=[string]$step.name
  $effect=$slide.TimeLine.MainSequence.AddEffect($shape,10,0,1)
  $effect.Timing.Duration=[double]$step.duration
 }
 foreach($video in $videos){
  $b=$video.box
  $shape=$pres.Slides.Item([int]$video.slide).Shapes.AddMediaObject2($video.resolvedPath,0,-1,[single]$b[0],[single]$b[1],[single]$b[2],[single]$b[3])
  $shape.Name=[string]$video.name
  $shape.AnimationSettings.PlaySettings.PlayOnEntry=([int][bool]$video.autoplay)*-1
  $shape.AnimationSettings.PlaySettings.LoopUntilStopped=([int][bool]$video.loop)*-1
 }
 $parent=Split-Path -Parent $dst
 if(-not (Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent | Out-Null}
 $pres.SaveAs($dst,24)
 [ordered]@{output=$dst;slides=$pres.Slides.Count;steps=$steps.Count;videos=$videos.Count;sha256=(Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash;playback_verified=$false} | ConvertTo-Json
} finally {
 if($null -ne $pres){$pres.Saved=-1;$pres.Close()}
 if($null -ne $app){if($initial -eq 0 -and $app.Presentations.Count -eq 0){$app.Quit()};[void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)}
}
