param([Parameter(Mandatory=$true)][string]$Source,[Parameter(Mandatory=$true)][string]$OutputDir,[switch]$EditProbe)
$ErrorActionPreference='Stop'
function Get-PptFileHash([string]$Path) {
 $stream=[IO.File]::OpenRead($Path)
 $sha=[Security.Cryptography.SHA256]::Create()
 try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
 finally { $stream.Dispose();$sha.Dispose() }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$app=$null;$pres=$null;$wb=$null;$initial=0
$r=[ordered]@{source=$Source;application='PowerPoint';opened=$false;slides=@();overflows=@();table_issues=@();font_issues=@();edit_probe=$false}
try {
 $app=New-Object -ComObject PowerPoint.Application
 $initial=$app.Presentations.Count
 $r.source_sha256=(Get-PptFileHash $Source)
 $r.version=$app.Version
 $pres=$app.Presentations.Open($Source,0,-1,0)
 $r.opened=$true;$r.slide_count=$pres.Slides.Count
 foreach($sl in $pres.Slides){
  $file=Join-Path $OutputDir ('slide-{0:D2}.png' -f $sl.SlideIndex)
  $sl.Export($file,'PNG',1920,1080)
  $count=[ordered]@{slide=$sl.SlideIndex;text=0;charts=0;pictures=0;tables=0;shapes=$sl.Shapes.Count}
  $textBoxes=@()
  $tableBoxes=@()
  foreach($sh in $sl.Shapes){
   if($sh.HasTextFrame -eq -1 -and $sh.TextFrame.HasText -eq -1){
    $count.text++
    $bound=$sh.TextFrame2.TextRange.BoundHeight
    if($bound -gt $sh.Height+3){$r.overflows+=@{slide=$sl.SlideIndex;name=$sh.Name;text=$sh.TextFrame.TextRange.Text;height=$sh.Height;bound=$bound}}
    $textBoxes+=@{name=$sh.Name;left=$sh.Left;top=$sh.Top;right=($sh.Left+$sh.Width);bottom=($sh.Top+$sh.Height);text=$sh.TextFrame.TextRange.Text}
    $fSize=$sh.TextFrame.TextRange.Font.Size
    if($fSize -gt 0 -and $fSize -lt 8){$r.font_issues+=@{slide=$sl.SlideIndex;name=$sh.Name;issue="tiny_font_pt:$fSize"}}
   }
   if($sh.HasChart -eq -1){$count.charts++}
   if($sh.HasTable -eq -1){
    $count.tables++
    $tbl=$sh.Table
    $tableBoxes+=@{name=$sh.Name;left=$sh.Left;top=$sh.Top;right=($sh.Left+$sh.Width);bottom=($sh.Top+$sh.Height)}
    $dataSizes=@()
    for($ri=2;$ri -le $tbl.Rows.Count;$ri++){
     for($ci=1;$ci -le $tbl.Columns.Count;$ci++){
      $cTxt=$tbl.Cell($ri,$ci).Shape.TextFrame.TextRange.Text.Trim()
      if($cTxt.Length -gt 0){
       $csz=[math]::Round($tbl.Cell($ri,$ci).Shape.TextFrame.TextRange.Font.Size,1)
       if($csz -gt 0 -and ($dataSizes -notcontains $csz)){$dataSizes+=$csz}
      }
     }
    }
    if($dataSizes.Count -gt 1){$r.table_issues+=@{slide=$sl.SlideIndex;name=$sh.Name;issue='inconsistent_data_font_pt';sizes=$dataSizes}}
   }
   if($sh.Type -eq 13){$count.pictures++}
  }
  foreach($tb in $tableBoxes){
   foreach($tx in $textBoxes){
    $ox=[math]::Min($tb.right,$tx.right)-[math]::Max($tb.left,$tx.left)
    $oy=[math]::Min($tb.bottom,$tx.bottom)-[math]::Max($tb.top,$tx.top)
    if($ox -gt 10 -and $oy -gt 3 -and $tx.top -gt $tb.top){
     $r.table_issues+=@{slide=$sl.SlideIndex;table=$tb.name;text_shape=$tx.name;issue='table_expands_into_text_below';overlap_pt=[math]::Round($oy,1)}
    }
   }
  }
  $count.preview_file=[IO.Path]::GetFileName($file)
  $count.preview_sha256=(Get-PptFileHash $file)
  $r.slides+= $count
 }
 if($EditProbe){
  $target=$null;$chartShape=$null;$chartSlide=0
  foreach($sl in $pres.Slides){foreach($sh in $sl.Shapes){
   if($null -eq $target -and $sh.HasTextFrame -eq -1 -and $sh.TextFrame.HasText -eq -1){$target=$sh;$targetSlide=$sl.SlideIndex}
   if($null -eq $chartShape -and $sh.HasChart -eq -1){$chartShape=$sh;$chartSlide=$sl.SlideIndex}
  }}
  if($null -eq $target){throw 'Missing editable text for probe'}
  $r.chart_probe_applicable=($null -ne $chartShape)
  $targetName=$target.Name;$oldLeft=$target.Left
  $target.TextFrame.TextRange.Text='编辑验证';$target.Left=$oldLeft+8
  if($r.chart_probe_applicable){
  $chart=$chartShape.Chart;$chartName=$chartShape.Name
  $chart.ChartData.Activate();$wb=$chart.ChartData.Workbook;$ws=$wb.Worksheets.Item(1)
  $old=$ws.Cells.Item(2,2).Value2
  $ws.Cells.Item(2,2).Value2=0.12345
  $chart.Refresh();$wb.Close($true);$wb=$null
  }
  $copy=Join-Path $OutputDir 'editing-probe.pptx';$pres.SaveAs($copy,24);$pres.Close();$pres=$null
  $pres=$app.Presentations.Open($copy,-1,0,0)
  $saved=$pres.Slides.Item($targetSlide).Shapes.Item($targetName)
  $r.text_persisted=($saved.TextFrame.TextRange.Text -eq '编辑验证')
  $r.move_persisted=([math]::Abs($saved.Left-$oldLeft-8) -lt 0.1)
  if($r.chart_probe_applicable){
  $chart=$pres.Slides.Item($chartSlide).Shapes.Item($chartName).Chart
  $chart.ChartData.Activate();$wb=$chart.ChartData.Workbook
  $r.workbook_value_persisted=($wb.Worksheets.Item(1).Cells.Item(2,2).Value2 -eq 0.12345)
  $wb.Close($false);$wb=$null
  }
  $r.edit_probe=($r.text_persisted -and $r.move_persisted -and (-not $r.chart_probe_applicable -or $r.workbook_value_persisted))
  if($r.chart_probe_applicable){$r.probe_original_value=$old}
 }
 $pres.Close();$pres=$null
 $r.source_unchanged=((Get-PptFileHash $Source) -eq $r.source_sha256)
 if(-not $r.source_unchanged){throw 'Source changed during validation'}
} catch {$r.error=$_.Exception.Message} finally {
 if($null -ne $wb){try{$wb.Close($false)}catch{}}
 if($null -ne $pres){try{$pres.Close()}catch{}}
 if($null -ne $app){if($initial -eq 0 -and $app.Presentations.Count -eq 0){$app.Quit()};[void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)}
}
$r.render_ok = $r.opened -and -not $r.Contains('error')
$r.quality_ok = $r.render_ok -and $r.overflows.Count -eq 0 -and $r.table_issues.Count -eq 0 -and $r.font_issues.Count -eq 0 -and (-not $EditProbe -or $r.edit_probe)
$r | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir 'powerpoint-validation.json') -Encoding UTF8
$r | ConvertTo-Json -Depth 8
if(-not $r.quality_ok){exit 1}
