param([Parameter(Mandatory=$true)][string]$Source,[Parameter(Mandatory=$true)][string]$OutputDir,[switch]$EditProbe)
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$app=$null;$pres=$null;$wb=$null;$initial=0
$r=[ordered]@{source=$Source;application='PowerPoint';opened=$false;slides=@();overflows=@();edit_probe=$false}
try {
 $app=New-Object -ComObject PowerPoint.Application
 $initial=$app.Presentations.Count
 $r.version=$app.Version
 $pres=$app.Presentations.Open($Source,0,0,0)
 $r.opened=$true;$r.slide_count=$pres.Slides.Count
 foreach($sl in $pres.Slides){
  $file=Join-Path $OutputDir ('slide-{0:D2}.png' -f $sl.SlideIndex)
  $sl.Export($file,'PNG',1920,1080)
  $count=[ordered]@{slide=$sl.SlideIndex;text=0;charts=0;pictures=0;tables=0;shapes=$sl.Shapes.Count}
  foreach($sh in $sl.Shapes){
   if($sh.HasTextFrame -eq -1 -and $sh.TextFrame.HasText -eq -1){
    $count.text++
    $bound=$sh.TextFrame2.TextRange.BoundHeight
    if($bound -gt $sh.Height+3){$r.overflows+=@{slide=$sl.SlideIndex;name=$sh.Name;text=$sh.TextFrame.TextRange.Text;height=$sh.Height;bound=$bound}}
   }
   if($sh.HasChart -eq -1){$count.charts++}
   if($sh.HasTable -eq -1){$count.tables++}
   if($sh.Type -eq 13){$count.pictures++}
  }
  $r.slides+= $count
 }
 if($EditProbe){
  $target=$null;$chartShape=$null;$chartSlide=0
  foreach($sl in $pres.Slides){foreach($sh in $sl.Shapes){
   if($null -eq $target -and $sh.HasTextFrame -eq -1 -and $sh.TextFrame.HasText -eq -1){$target=$sh;$targetSlide=$sl.SlideIndex}
   if($null -eq $chartShape -and $sh.HasChart -eq -1){$chartShape=$sh;$chartSlide=$sl.SlideIndex}
  }}
  if($null -eq $target -or $null -eq $chartShape){throw 'Missing editable text/chart for probe'}
  $targetName=$target.Name;$oldLeft=$target.Left
  $target.TextFrame.TextRange.Text='编辑验证';$target.Left=$oldLeft+8
  $chart=$chartShape.Chart;$chartName=$chartShape.Name
  $chart.ChartData.Activate();$wb=$chart.ChartData.Workbook;$ws=$wb.Worksheets.Item(1)
  $old=$ws.Cells.Item(2,2).Value2
  $ws.Cells.Item(2,2).Value2=0.12345
  $chart.Refresh();$wb.Close($true);$wb=$null
  $copy=Join-Path $OutputDir 'editing-probe.pptx';$pres.SaveAs($copy,24);$pres.Close();$pres=$null
  $pres=$app.Presentations.Open($copy,-1,0,0)
  $saved=$pres.Slides.Item($targetSlide).Shapes.Item($targetName)
  $r.text_persisted=($saved.TextFrame.TextRange.Text -eq '编辑验证')
  $r.move_persisted=([math]::Abs($saved.Left-$oldLeft-8) -lt 0.1)
  $chart=$pres.Slides.Item($chartSlide).Shapes.Item($chartName).Chart
  $chart.ChartData.Activate();$wb=$chart.ChartData.Workbook
  $r.workbook_value_persisted=($wb.Worksheets.Item(1).Cells.Item(2,2).Value2 -eq 0.12345)
  $wb.Close($false);$wb=$null
  $r.edit_probe=($r.text_persisted -and $r.move_persisted -and $r.workbook_value_persisted)
  $r.probe_original_value=$old
 }
 $pres.Close();$pres=$null
} catch {$r.error=$_.Exception.Message} finally {
 if($null -ne $wb){try{$wb.Close($false)}catch{}}
 if($null -ne $pres){try{$pres.Close()}catch{}}
 if($null -ne $app){if($initial -eq 0 -and $app.Presentations.Count -eq 0){$app.Quit()};[void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)}
}
$r | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir 'powerpoint-validation.json') -Encoding UTF8
$r | ConvertTo-Json -Depth 8
if($r.Contains('error')){exit 1}
