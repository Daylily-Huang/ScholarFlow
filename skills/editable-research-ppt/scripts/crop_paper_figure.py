"""Render a PDF figure rectangle without rewriting it. Optional PyMuPDF required."""
import argparse
import hashlib
import json
from pathlib import Path


def crop(pdf, output, page, bbox, *, paper_id, figure, caption, source, verified_complete=False, dpi=240):
    import fitz
    pdf, output = Path(pdf).resolve(), Path(output).resolve()
    if output.exists() or output.with_suffix('.json').exists():
        raise ValueError('Output already exists; choose a new path')
    if not (72 <= dpi <= 600):
        raise ValueError('DPI must be 72..600')
    with fitz.open(pdf) as doc:
        if page < 1 or page > len(doc):
            raise ValueError('Page outside PDF')
        rect=fitz.Rect(bbox)
        bounds=doc[page-1].rect
        if rect.is_empty or rect.is_infinite or not bounds.contains(rect):
            raise ValueError('Crop rectangle outside PDF page')
        pix=doc[page-1].get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),clip=rect,alpha=False)
        output.parent.mkdir(parents=True,exist_ok=True)
        pix.save(output)
    record={'kind':'paper_crop','path':str(output),'caption':caption,'source':source,
            'provenance':{'paper_id':paper_id,'figure':figure,'page':page,'crop_bbox':list(bbox),
                          'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
                          'png_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                          'render_method':'pdf_clip','dpi':dpi,'verified_complete':verified_complete}}
    output.with_suffix('.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf',required=True);p.add_argument('--output',required=True)
    p.add_argument('--page',required=True,type=int)
    p.add_argument('--bbox',required=True,nargs=4,type=float,metavar=('X0','Y0','X1','Y1'))
    p.add_argument('--paper-id',required=True);p.add_argument('--figure',required=True)
    p.add_argument('--caption',required=True);p.add_argument('--source',required=True)
    p.add_argument('--dpi',type=int,default=240)
    p.add_argument('--verified-complete',action='store_true',help='Only after visual check of axes, legend, panels and context')
    args=vars(p.parse_args())
    try:print(json.dumps(crop(**args),ensure_ascii=False,indent=2))
    except ImportError:p.exit(2,'PDF cropping needs optional PyMuPDF: python -m pip install pymupdf\n')
    except ValueError as e:p.exit(2,str(e)+'\n')
