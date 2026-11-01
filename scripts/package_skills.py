"""Build the three standalone bundles from pinned Git blobs, never from a dirty checkout."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'docs/releases/skills-2026-11-01/release.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_files(commit, paths):
    proc = subprocess.Popen(['git', 'archive', '--format=tar', commit, '--', *paths], cwd=str(ROOT), stdout=subprocess.PIPE)
    result = {}
    try:
        with tarfile.open(fileobj=proc.stdout, mode='r|') as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts or member.issym() or member.islnk():
                    raise ValueError('Unsafe Git archive entry')
                if member.isfile():
                    if '__pycache__' in name.parts or name.suffix == '.pyc':
                        continue
                    result[member.name] = archive.extractfile(member).read()
    finally:
        proc.stdout.close()
        if proc.wait():
            raise ValueError('Pinned Git archive failed')
    return result


def instructions(component, version):
    extra = ''
    if component == 'literature-discovery-acquisition':
        extra = ('\n本包同时安装 shared 和 schemas；能力文档在技能目录内的 docs/，不要只复制技能文件夹。升级会更新这两个共享目录，'
                 '先核对与其他 ScholarFlow 技能的版本并备份。\n'
                 '免费 Key 配置教程在 literature-discovery-acquisition/references/openalex_api_key_setup.md；'
                 '不需要把 Key 发给任何人。安装不会申请 Key、设置环境变量或联网查询。\n')
    if component == 'editable-research-ppt':
        extra = ('\n随包保留模板、字体、图标及第三方许可。安装器不安装字体或更改系统设置；'
                 '如需随包字体，由你按技能说明运行 scripts/install_fonts.py。\n')
    return ('# ' + component + ' v' + version + ' 安装与升级\n\n'
            '完整解压 ZIP，在有 install.py 的目录打开终端。需要 Python；PPT 为 3.10+，其余为 3.9+。'
            '先确认你的 AI 助手实际读取的 skills 目录，不要原样照抄占位路径。\n\n'
            '```text\npython install.py --target "<AI助手实际读取的skills目录>"\n```\n\n'
            '例如 Codex 通常为用户目录下 .codex/skills，Claude Code 通常为 .claude/skills；'
            '以宿主实际配置为准。安装后重新加载技能或重启宿主。\n\n'
            '重复安装相同版本会直接返回 already-current，不重复覆盖。已有版本或自定义文件有差异时会停止。'
            '确认升级后，选一个与安装目录同盘、尚不存在且位于安装目录外的备份路径：\n\n'
            '```text\npython install.py --target "<skills目录>" --replace --backup "<同盘的新备份目录>"\n```\n\n'
            '旧文件会完整保留到备份目录；只处理本包列出的目录，其他技能目录不动。'
            '请保留原 ZIP 和校验文件；自定义文件先比较再迁移。\n' + extra +
            '\n技能升级不会自动重建旧 HTML/PPT，也不修改论文、实验数据、批注或已有成果。'
            '代码与教学内容、论文原图、字体和图标的许可证分别适用，保留各自声明。\n')


def relocate_links(payload, commit):
    """Keep bundled links local; optional other skills remain pinned online references."""
    adjustments = []
    for name in list(payload):
        if not name.endswith('.md'):
            continue
        old = payload[name]
        text = old.decode('utf-8-sig')
        original = 'skills/' + name if not name.startswith(('shared/', 'schemas/', 'docs/')) else name
        if name.startswith('literature-discovery-acquisition/docs/'):
            original = name[len('literature-discovery-acquisition/'):]
        def replace(match):
            label, link = match.group(1), match.group(2)
            if not link or re.match(r'^[a-zA-Z]+:', link) or link.startswith(('#', '/')) or ' ' in link:
                return match.group(0)
            path, mark, anchor = link.partition('#')
            source_path = posixpath.normpath(posixpath.join(posixpath.dirname(original), path))
            target = source_path[len('skills/'):] if source_path.startswith('skills/') else source_path
            bundled_doc = 'literature-discovery-acquisition/' + source_path
            if source_path.startswith('docs/') and bundled_doc in payload:
                target = bundled_doc
            if target in payload:
                url = posixpath.relpath(target, posixpath.dirname(name))
            elif source_path.startswith('skills/'):
                url = 'https://github.com/Daylily-Huang/ScholarFlow/blob/' + commit + '/' + source_path
            else:
                return match.group(0)
            return '[' + label + '](' + url + (mark + anchor if mark else '') + ')'
        updated = re.sub(r'\[([^\]]*)\]\(([^)]+)\)', replace, text)
        if updated != text:
            payload[name] = updated.encode('utf-8')
            adjustments.append(name)
    return adjustments


def verify_bundle(archive, component):
    with tempfile.TemporaryDirectory(prefix='bundle-check-', dir=str(archive.parent)) as temp:
        temp = Path(temp)
        source, target = temp / 'source', temp / 'installed'
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            if len(names) != len(set(names)) or any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n or ':' in n for n in names):
                raise ValueError('Unsafe or duplicate ZIP entries')
            z.extractall(source)
        target.mkdir()
        (target / 'unrelated-skill').mkdir()
        (target / 'unrelated-skill/keep.txt').write_text('keep', encoding='utf-8')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
        env.pop('PYTHONPATH', None)
        env.pop('OPENALEX_API_KEY', None)
        def run(args):
            r = subprocess.run([sys.executable, '-I', '-S', '-B', *map(str, args)], cwd=str(temp), env=env,
                               capture_output=True, text=True, encoding='utf-8')
            if r.returncode:
                raise ValueError('Bundle probe failed: ' + r.stdout + r.stderr)
            return r.stdout
        for _ in range(2):
            run([source / 'install.py', '--target', target])
        if (target / 'unrelated-skill/keep.txt').read_text(encoding='utf-8') != 'keep':
            raise ValueError('Another installed skill was changed')
        scripts = target / component / 'scripts'
        if component == 'paper-close-read':
            run([scripts / 'selftest.py', '--work-dir', temp / 'reader-selftest'])
        elif component == 'editable-research-ppt':
            run([scripts / 'verify_release.py'])
            run([scripts / 'generate.py', '--input', target / component / 'assets/examples/adaptive-solid.json', '--output', temp / 'sample.pptx'])
            run([scripts / 'audit.py', temp / 'sample.pptx', '--strict'])
        else:
            result = json.loads(run([scripts / 'openalex_access.py']))
            if result['key_configured'] or result['online_validation'] != 'NOT_RUN':
                raise ValueError('Offline check used a key or network')
            run([scripts / 'agent_search.py', '--version'])
        return {'installed_twice': True, 'unrelated_skill_preserved': True, 'isolated_runtime_probe': 'PASS'}


def build(config, output, verify=False):
    config = json.loads(Path(config).read_text(encoding='utf-8'))
    commit = config['source_commit']
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('A full pinned source commit is required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    installer = (ROOT / 'scripts/standalone_skill_installer.py').read_bytes()
    recipe = sha(Path(__file__).read_bytes() + installer)
    rows = []
    for component in config['components']:
        name, version = component['name'], component['version']
        roots = [name]
        paths = ['skills/' + name, 'LICENSE']
        if name == 'literature-discovery-acquisition':
            roots += ['shared', 'schemas']
            paths += ['shared', 'schemas', 'docs/CAPABILITY_STATUS.md']
        original = git_files(commit, paths)
        payload = {k[len('skills/'):] if k.startswith('skills/') else k: v for k, v in original.items()}
        if name == 'literature-discovery-acquisition':
            payload[name + '/docs/CAPABILITY_STATUS.md'] = payload.pop('docs/CAPABILITY_STATUS.md')
        if name == 'editable-research-ppt':
            actual_version = json.loads(payload[name + '/assets/template-system.json'])['version']
        else:
            code = payload[name + '/scripts/build_html.py'] if name == 'paper-close-read' else payload['shared/version.py']
            variable = 'GENERATOR_VERSION' if name == 'paper-close-read' else 'PROJECT_VERSION'
            actual_version = next(ast.literal_eval(node.value) for node in ast.parse(code.decode('utf-8-sig')).body
                                  if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable for t in node.targets))
        if version != actual_version:
            raise ValueError('Configured version differs from pinned source: ' + name)
        # Each source skill retains its native files; discovery additionally retains the repository MIT license.
        if name + '/LICENSE' not in payload:
            payload[name + '/LICENSE'] = payload['LICENSE']
        if name == 'literature-discovery-acquisition':
            payload['shared/LICENSE'] = payload['LICENSE']
        adjustments = relocate_links(payload, commit) if name == 'literature-discovery-acquisition' else []
        payload['install.py'] = installer
        guide = instructions(name, version).encode('utf-8')
        payload['INSTALL.zh-CN.md'] = guide
        manifest = {'component': name, 'version': version, 'release_tag': config['tag'],
                    'skill_source_commit': commit, 'packaging_recipe_sha256': recipe,
                    'minimum_python': component['minimum_python'], 'install_roots': roots,
                    'relative_links_relocated': adjustments,
                    'files': {k: sha(v) for k, v in sorted(payload.items())}}
        payload['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        archive = output / (name + '-v' + version + '.zip')
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path, raw in sorted(payload.items()):
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, raw)
        (output / (name + '-v' + version + '.manifest.json')).write_bytes(payload['manifest.json'])
        (output / (name + '-INSTALL.zh-CN.md')).write_bytes(guide)
        row = {'component': name, 'version': version, 'archive': archive.name,
               'files': len(payload), 'sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size}
        if verify:
            row['verification'] = verify_bundle(archive, name)
        rows.append(row)
    (output / 'release-index.json').write_text(json.dumps({'release': config, 'packages': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    files = sorted(p for p in output.iterdir() if p.is_file() and p.name != 'SHA256SUMS.txt')
    (output / 'SHA256SUMS.txt').write_text(''.join(sha(p.read_bytes()) + '  ' + p.name + '\n' for p in files), encoding='utf-8')
    return rows


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--verify', action='store_true')
    a = p.parse_args()
    print(json.dumps(build(a.config, a.output, a.verify), ensure_ascii=False, indent=2))
