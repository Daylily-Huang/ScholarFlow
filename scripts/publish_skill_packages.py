"""Publish verified packages from GitHub Actions after the same main commit passes CI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request


def publish(config_path, directory, expected_ci_sha):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    directory = Path(directory)
    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    if not token or repo != 'Daylily-Huang/ScholarFlow' or not re.fullmatch('[0-9a-f]{40}', expected_ci_sha):
        raise ValueError('An authorized repository Actions token and exact CI commit are required')
    base = 'https://api.github.com/repos/' + repo
    def request(url, method='GET', data=None, content_type='application/json', size=None):
        if not url.startswith((base + '/', 'https://uploads.github.com/repos/' + repo + '/')):
            raise ValueError('Unexpected API destination')
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'ScholarFlow-package-release',
                   'X-GitHub-Api-Version': '2026-03-10'}
        if data is not None:
            headers['Content-Type'] = content_type
        if size is not None:
            headers['Content-Length'] = str(size)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        req.add_unredirected_header('Authorization', 'Bearer ' + token)
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)
    # Bounded CI gate, bound to this publishing commit rather than a previous green run.
    deadline = time.monotonic() + 600
    while True:
        runs = request(base + '/actions/runs?head_sha=' + expected_ci_sha)['workflow_runs']
        matching = [r for r in runs if r['name'] == 'tests' and r['event'] == 'push' and r['head_sha'] == expected_ci_sha]
        if matching and matching[0]['status'] == 'completed':
            if matching[0]['conclusion'] != 'success':
                raise ValueError('Exact main-commit CI did not succeed; release remains unpublished')
            break
        if time.monotonic() >= deadline:
            raise ValueError('Timed out waiting for exact main-commit CI; no release published')
        time.sleep(15)
    expected = {}
    for line in (directory / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        value, name = line.split('  ', 1)
        if Path(name).name != name or '/' in name or '\\' in name or ':' in name or name in expected:
            raise ValueError('Unsafe or duplicate release asset name')
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != value:
            raise ValueError('Release asset checksum differs: ' + name)
        expected[name] = value
    index = json.loads((directory / 'release-index.json').read_text(encoding='utf-8'))
    if index['release'] != config or len(index['packages']) != len(config['components']):
        raise ValueError('Release configuration differs from verified packages')
    for package in index['packages']:
        if not all(package.get('verification', {}).get(k) for k in ('installed_twice', 'unrelated_skill_preserved')):
            raise ValueError('Package installation was not verified')
        if package['verification'].get('isolated_runtime_probe') != 'PASS':
            raise ValueError('Isolated runtime check was not verified')
        if expected.get(package['archive']) != package['sha256']:
            raise ValueError('Package index and checksums differ')
    expected['SHA256SUMS.txt'] = hashlib.sha256((directory / 'SHA256SUMS.txt').read_bytes()).hexdigest()
    if set(p.name for p in directory.iterdir() if p.is_file()) != set(expected):
        raise ValueError('Unexpected files in publication directory')
    def actual_tag_commit():
        obj = request(base + '/git/ref/tags/' + urllib.parse.quote(config['tag'], safe=''))['object']
        for _ in range(16):
            if not re.fullmatch('[0-9a-f]{40}', obj.get('sha', '')):
                raise ValueError('Invalid release tag object')
            if obj['type'] == 'commit':
                return obj['sha']
            if obj['type'] != 'tag':
                raise ValueError('Release tag does not resolve to a commit')
            obj = request(base + '/git/tags/' + obj['sha'])['object']
        raise ValueError('Release annotated-tag chain is too deep')
    try:
        tag_commit = actual_tag_commit()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        # Create a missing lightweight ref once; never move or delete an existing tag.
        try:
            request(base + '/git/refs', 'POST', json.dumps({'ref': 'refs/tags/' + config['tag'],
                                                         'sha': config['source_commit']}).encode('utf-8'))
        except urllib.error.HTTPError as conflict:
            if conflict.code != 422:
                raise
        tag_commit = actual_tag_commit()
    if tag_commit != config['source_commit']:
        raise ValueError('Actual release tag points at a different source; no release published')
    tag_url = base + '/releases/tags/' + urllib.parse.quote(config['tag'], safe='')
    try:
        release = request(tag_url)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        body = (config['name'] + '\n\n三个独立 ZIP 均含 install.py、完整清单与中文安装/升级说明。'
                '文献检索包包含共享引擎、Schema 与免费 OpenAlex Key 教程；无需克隆仓库。\n\n'
                '技能源码固定于 `' + config['source_commit'] + '`；发布与构建脚本提交 `' + expected_ci_sha + '`。'
                '先按 SHA256SUMS.txt 校验并完整解压，再按对应 INSTALL.zh-CN.md 安装。'
                '旧版本和自定义文件有差异时，安装器要求显式替换并保留备份。'
                '字体、图标、论文等第三方许可保持各自声明；本次不覆盖历史 Release。\n\n'
                '未使用真实 OpenAlex Key 进行在线认证，不自动注册或修改个人配置。')
        release = request(base + '/releases', 'POST', json.dumps({'tag_name': config['tag'],
                          'target_commitish': config['source_commit'], 'name': config['name'], 'body': body,
                          'draft': True, 'prerelease': False}).encode('utf-8'))
    assets = {a['name']: a for a in release['assets']}
    if release['tag_name'] != config['tag'] or release['target_commitish'] != config['source_commit']:
        raise ValueError('Existing release points at a different source; refusing to change it')
    if set(assets) - set(expected):
        raise ValueError('Existing release contains unreviewed extra assets; refusing to publish it')
    if not release['draft'] and set(assets) != set(expected):
        raise ValueError('Existing published release differs; refusing to replace or delete assets')
    for name, checksum in expected.items():
        if name not in assets:
            if not release['draft']:
                raise ValueError('Refusing to modify an already published release')
            path = directory / name
            url = 'https://uploads.github.com/repos/' + repo + '/releases/' + str(release['id']) + '/assets?name=' + urllib.parse.quote(name)
            with path.open('rb') as stream:
                assets[name] = request(url, 'POST', stream, 'application/octet-stream', path.stat().st_size)
        # GitHub hashes uploaded bytes on the server. Missing digest is not a pass.
        if assets[name].get('digest') != 'sha256:' + checksum:
            raise ValueError('Server asset digest differs or is unavailable: ' + name)
    # Recheck after uploads as well, since a tag may have moved while assets were transferring.
    if actual_tag_commit() != config['source_commit']:
        raise ValueError('Release tag changed during upload; draft kept unpublished')
    if release['draft']:
        release = request(base + '/releases/' + str(release['id']), 'PATCH',
                          json.dumps({'draft': False, 'make_latest': 'true'}).encode('utf-8'))
    return {'release': release['html_url'], 'assets_verified': len(expected), 'published': not release['draft']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--directory', required=True, type=Path)
    p.add_argument('--expected-ci-sha', required=True)
    args = p.parse_args()
    print(json.dumps(publish(args.config, args.directory, args.expected_ci_sha), indent=2))
