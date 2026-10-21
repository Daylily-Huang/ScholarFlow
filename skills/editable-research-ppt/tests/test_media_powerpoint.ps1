param([Parameter(Mandatory=$true)][string]$WorkDir)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$work=[IO.Path]::GetFullPath($WorkDir)
if(Test-Path -LiteralPath $work){throw 'Use a new test directory; existing files are preserved'}
New-Item -ItemType Directory -Path $work | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'examples/media') -Destination (Join-Path $work 'fixture') -Recurse
$f=Join-Path $work 'fixture';$base=Join-Path $f 'base.pptx';$config=Join-Path $f 'effects.json';$output=Join-Path $work 'result.pptx'
$script=Join-Path $root 'scripts/add_media.ps1';$baseline=(Get-FileHash $base).Hash
$checks=[ordered]@{}
function Reject($source,$cfg,$dest){
 $rejected=$false
 try{& $script -Source $source -Config $cfg -Output $dest | Out-Null}catch{$rejected=$true}
 if(-not $rejected){throw 'Invalid request was accepted'}
}
Reject $base $config $base;$checks.source_protected=((Get-FileHash $base).Hash -eq $baseline)
$sentinel=Join-Path $work 'existing.pptx';[IO.File]::WriteAllText($sentinel,'user file')
Reject $base $config $sentinel;$checks.existing_output_protected=([IO.File]::ReadAllText($sentinel) -eq 'user file')
& $script -Source $base -Config $config -Output $output | Out-Null
Reject $output $config (Join-Path $work 'bad-existing-animation.pptx')
$checks.existing_animation_protected=(-not(Test-Path (Join-Path $work 'bad-existing-animation.pptx')))
$bad=Get-Content $config -Raw -Encoding UTF8 | ConvertFrom-Json
$bad.steps[0].shapes=@('missing-shape');$badFile=Join-Path $f 'bad.json';$bad | ConvertTo-Json -Depth 8 | Set-Content $badFile -Encoding UTF8
Reject $base $badFile (Join-Path $work 'bad-shape.pptx')
$checks.missing_shape_rejected=(-not(Test-Path (Join-Path $work 'bad-shape.pptx')))
$bad=Get-Content $config -Raw -Encoding UTF8 | ConvertFrom-Json
$bad.videos[0].box=@(0,0,99999,99999);$bad | ConvertTo-Json -Depth 8 | Set-Content $badFile -Encoding UTF8
Reject $base $badFile (Join-Path $work 'bad-box.pptx')
$checks.bad_box_rejected=(-not(Test-Path (Join-Path $work 'bad-box.pptx')))
$app=$null;$p=$null;$win=$null;$initial=0
try{
 $app=New-Object -ComObject PowerPoint.Application;$initial=$app.Presentations.Count
 $p=$app.Presentations.Open($output,0,0,-1)
 $checks.effect_count=($p.Slides.Item(1).TimeLine.MainSequence.Count -eq 3)
 $checks.static_fallback=($p.Slides.Item(3).TimeLine.MainSequence.Count -eq 0)
 $win=$p.SlideShowSettings.Run();$indices=@($win.View.GetClickIndex())
 for($i=1;$i -le 3;$i++){$win.View.Next();Start-Sleep -Milliseconds 800;$indices+= $win.View.GetClickIndex()}
 $checks.click_sequence=(($indices -join ',') -eq '0,1,2,3');$win.View.Exit();$win=$null
 $shape=$p.Slides.Item(1).Shapes.Item('step-1').GroupItems.Item('head0')
 $shape.TextFrame.TextRange.Text='EDIT CHECK'
 $p.Slides.Item(1).TimeLine.MainSequence.Item(1).Timing.Duration=0.9
 $edit=Join-Path $work 'edited.pptx';$p.SaveAs($edit,24);$p.Close();$p=$null
 $p=$app.Presentations.Open($edit,-1,0,0)
 $checks.saved_text=($p.Slides.Item(1).Shapes.Item('step-1').GroupItems.Item('head0').TextFrame.TextRange.Text -eq 'EDIT CHECK')
 $checks.saved_timing=([math]::Abs($p.Slides.Item(1).TimeLine.MainSequence.Item(1).Timing.Duration-0.9) -lt 0.01)
 $p.Close();$p=$null
 # Render the actual embedded video. Do not mutate or save the candidate.
 $p=$app.Presentations.Open($output,0,0,0);$p.Slides.Item(3).Delete();$p.Slides.Item(1).Delete()
 $video=Join-Path $work 'embedded-playback.mp4';$p.CreateVideo($video,$false,9,720,20,85)
 $limit=(Get-Date).AddSeconds(120)
 do{Start-Sleep -Seconds 2;$status=$p.CreateVideoStatus}while($status -in @(0,1,2) -and (Get-Date) -lt $limit)
 $checks.video_export=($status -eq 3 -and (Test-Path -LiteralPath $video))
 $p.Saved=-1;$p.Close();$p=$null
}catch{Write-Output ('Failure at line '+$_.InvocationInfo.ScriptLineNumber+': '+$_.Exception.Message);throw}finally{if($null -ne $win){try{$win.View.Exit()}catch{}};if($null -ne $p){try{$p.Saved=-1;$p.Close()}catch{}};if($null -ne $app -and $initial -eq 0 -and $app.Presentations.Count -eq 0){$app.Quit()}}
$checks.source_unchanged=((Get-FileHash $base).Hash -eq $baseline)
$pass=-not($checks.Values -contains $false)
@{passed=$pass;checks=$checks;result_sha256=(Get-FileHash $output).Hash;scope='Windows desktop PowerPoint; exported video still requires frame inspection'} | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $work 'validation.json') -Encoding UTF8
$checks | ConvertTo-Json
if(-not $pass){exit 1}
