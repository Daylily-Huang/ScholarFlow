"""Refresh the release file manifest and current snapshot after design approval."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST='SHA256SUMS.txt'


def load_module(root,name):
    spec=importlib.util.spec_from_file_location(name,root/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def json_file(path):
    return json.loads(path.read_bytes())


def with_newlines(path,text):
    raw=path.read_bytes()
    return text.replace('\n','\r\n' if b'\r\n' in raw else '\n').encode('utf-8')


def proposed(root):
    release=load_module(root,'verify_release')
    publication=load_module(root,'verify_publication')
    errors=publication.check_design(root)
    standard=json_file(root/'references/approved-standard.json')
    system=json_file(root/'assets/template-system.json')
    version=system['version']
    if standard['current_version']!=version:
        errors.append('Approved standard version does not match the release')
    files=release.package_files(root)
    digests={name:publication.digest(path) for name,path in files.items()}
    for group in ('design_files','approved_examples','current_examples'):
        for name,digest in standard.get(group,{}).items():
            if digests.get(name)!=digest:
                errors.append(f'Approved asset drift: {name}')
    if errors:
        raise ValueError('Release records cannot approve design drift: '+'; '.join(errors))

    snapshot=f'references/v{version}-hashes.json'
    record=json_file(root/snapshot)
    if record['version']!=version:
        raise ValueError('Current release snapshot has the wrong version')
    record['sha256']={name:digests[name] for name in record['sha256']}
    snapshot_bytes=with_newlines(root/snapshot,json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    import hashlib
    digests[snapshot]=hashlib.sha256(snapshot_bytes).hexdigest()
    manifest=''.join(f'{digests[name]}  {name}\n' for name in sorted(digests))
    return version,{snapshot:snapshot_bytes,MANIFEST:with_newlines(root/MANIFEST,manifest)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true')
    mode.add_argument('--write',action='store_true')
    args=parser.parse_args(argv)
    root=args.root.resolve()
    try:
        version,payloads=proposed(root)
        drift=[name for name,data in payloads.items() if (root/name).read_bytes()!=data]
        if args.write:
            for name in drift:
                (root/name).write_bytes(payloads[name])
        report={'ok':args.write or not drift,'version':version,'drift':[] if args.write else drift}
    except (OSError,ValueError,KeyError) as exc:
        report={'ok':False,'error':str(exc)}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ok'] else 2


if __name__=='__main__':
    raise SystemExit(main())
