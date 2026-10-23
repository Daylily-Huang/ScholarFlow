"""Export a generated bilingual reader using a locally installed Chrome/Chromium."""
import argparse
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlencode


def find_browser(explicit=None):
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path.resolve())
        raise ValueError('指定的浏览器文件不存在：' + str(path))
    candidates = [shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser', 'chrome', 'msedge')]
    for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        root = os.environ.get(variable)
        if root:
            candidates.extend(str(Path(root) / relative) for relative in (
                'Google/Chrome/Application/chrome.exe', 'Microsoft/Edge/Application/msedge.exe'))
    candidates.append('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise ValueError('未找到 Chrome/Chromium/Edge。可用 --browser 指定浏览器；也可在 HTML 中点击「导出双语 PDF」。')


def export_pdf(source, output, work_dir, browser=None, paper='landscape', notes=True, aux=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.suffix.lower() != '.pdf':
        raise ValueError('输出必须是独立的 .pdf 文件，不能覆盖 HTML')
    text = source.read_text(encoding='utf-8-sig')
    if 'window.readerPDF={prepare,restore}' not in text:
        raise ValueError('请先用新版 paper-close-read 重建 HTML；输入页不含双语 PDF 排版器')
    executable = find_browser(browser)
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    url = source.as_uri() + '?' + urlencode({'reader-pdf': '1', 'paper': paper, 'notes': '1' if notes else '0', 'aux': '1' if aux else '0'})
    with tempfile.TemporaryDirectory(prefix='reader-pdf-', dir=str(work_dir)) as temporary:
        root = Path(temporary)
        rendered = root / 'rendered.pdf'
        command = [executable, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                   '--disable-background-networking', '--disable-extensions', '--no-pdf-header-footer',
                   '--user-data-dir=' + str(root / 'profile'), '--virtual-time-budget=4000']
        prepared = subprocess.run(command + ['--dump-dom', url], capture_output=True, timeout=120)
        markup = prepared.stdout.decode('utf-8', errors='replace')
        if prepared.returncode or 'data-reader-pdf-ready="true"' not in markup or 'class="pdf-pair"' not in markup:
            raise ValueError('双语排版未完成；请先在浏览器检查此 HTML，原输出保持不变')
        # Freeze the verified print DOM. A second browser pass must not rerun reader state.
        frozen = root / 'prepared.html'
        frozen.write_text(re.sub(r'<script\b[^>]*>[\s\S]*?</script\s*>', '', markup, flags=re.I), encoding='utf-8')
        result = subprocess.run(command + ['--print-to-pdf=' + str(rendered), frozen.as_uri()], capture_output=True, timeout=120)
        if result.returncode or not rendered.is_file() or not rendered.read_bytes().startswith(b'%PDF-'):
            raise ValueError('浏览器未能生成 PDF（退出码 ' + str(result.returncode) + '）；原输出保持不变')
        output.parent.mkdir(parents=True, exist_ok=True)
        pending = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.reader-pdf-', dir=str(output.parent), delete=False) as stream:
                pending = Path(stream.name)
                stream.write(rendered.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(pending), str(output))
        finally:
            if pending is not None and pending.exists():
                pending.unlink()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--work-dir', required=True, type=Path, help='临时目录，用于隔离浏览器 profile 和排版中间件')
    parser.add_argument('--browser')
    parser.add_argument('--paper', choices=('landscape', 'portrait'), default='landscape')
    parser.add_argument('--no-explanations', action='store_true')
    parser.add_argument('--include-aux', action='store_true')
    args = parser.parse_args()
    try:
        target = export_pdf(args.html, args.output, args.work_dir, args.browser, args.paper, not args.no_explanations, args.include_aux)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.exit(2, 'PDF 导出未完成：' + str(exc) + '\n')
    print(str(target))


if __name__ == '__main__':
    main()
