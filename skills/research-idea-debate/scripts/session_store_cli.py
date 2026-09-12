#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research-idea-debate 会话持久化 CLI。

封装 `shared.execution.session_store.SessionStore`，供技能在每轮结束时落盘、
检查点写入快照、以及会话恢复时重放事件。

用法：
    python session_store_cli.py append   <session_dir> --event-json '<json>'
    python session_store_cli.py rebuild  <session_dir>
    python session_store_cli.py check    <session_dir>
    python session_store_cli.py recover  <session_dir>
    python session_store_cli.py snapshot <session_dir> --expected-revision N --session-json '<json>'
    python session_store_cli.py seal     <session_dir> --expected-revision N [--session-json '<json>']
    python session_store_cli.py append-usage <session_dir> --entry-json '<json>'

退出码：0 成功；1 校验/一致性失败（如中段损坏、revision 冲突）；2 输入错误。

**不使用 `sys.exit` 打印堆栈**：所有失败都转成结构化 JSON 输出，便于上游编排读取。
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_ROOT = os.path.dirname(_HERE)


def _ensure_import_path():
    """把仓库根或安装根加入 sys.path，使 `shared.execution` 可导入。

    仓库布局：`<repo>/skills/<skill>/scripts/` → 上溯 3 级得到 `<repo>`。
    安装布局：`<dest>/skills/<skill>/scripts/` 或 `<dest>/<skill>/scripts/`，
    两种情况上溯 3 级都能得到含 `shared/` 的根（install.sh 会复制 `shared/`）。
    """
    for cand in (
        os.path.dirname(os.path.dirname(_SKILL_ROOT)),
        os.path.dirname(_SKILL_ROOT),
        _SKILL_ROOT,
    ):
        if os.path.isdir(os.path.join(cand, "shared")):
            if cand not in sys.path:
                sys.path.insert(0, cand)
            return cand
    raise ImportError("找不到 shared/ 引擎目录；请从完整检出或已安装树运行")


def _store(session_dir):
    _ensure_import_path()
    from shared.execution import SessionStore
    return SessionStore(session_dir)


def _emit(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def _parse(text, what):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("%s 不是合法 JSON：%s" % (what, exc))


def main(argv=None):
    ap = argparse.ArgumentParser(description="research-idea-debate 会话持久化 CLI")
    ap.add_argument("command", choices=[
        "append", "rebuild", "check", "recover", "snapshot", "seal", "append-usage",
        "read-usage",
    ])
    ap.add_argument("session_dir")
    ap.add_argument("--event-json")
    ap.add_argument("--session-json")
    ap.add_argument("--entry-json")
    ap.add_argument("--expected-revision", type=int)
    args = ap.parse_args(argv)

    try:
        store = _store(args.session_dir)
    except ImportError as exc:
        return _emit({"status": "INPUT_ERROR", "error": str(exc)}, 2)

    from shared.execution import CorruptEventLog, RevisionConflict, ProjectionError

    try:
        if args.command == "append":
            if not args.event_json:
                return _emit({"status": "INPUT_ERROR", "error": "append 需要 --event-json"}, 2)
            applied = store.append_event(_parse(args.event_json, "--event-json"))
            return _emit({"status": "OK", "applied": applied,
                          "note": "applied=false 表示 event_id 已存在，幂等跳过"})

        if args.command == "rebuild":
            report = store.rebuild()
            return _emit({"status": "OK", **report})

        if args.command == "check":
            report = store.consistency_report()
            return _emit({"status": "OK" if report["consistent"] else "INCONSISTENT", **report},
                         0 if report["consistent"] else 1)

        if args.command == "recover":
            return _emit({"status": "OK", **store.recover()})

        if args.command == "snapshot":
            if args.expected_revision is None:
                return _emit({"status": "INPUT_ERROR", "error": "snapshot 需要 --expected-revision"}, 2)
            if args.session_json:
                session = _parse(args.session_json, "--session-json")
            else:
                session = store.load_snapshot()
            saved = store.save_snapshot(session, args.expected_revision)
            return _emit({"status": "OK", "revision": saved["revision"]})

        if args.command == "seal":
            # 事件先行：封存可信重放基底（checkpoint.json）+ 快照。
            if args.expected_revision is None:
                return _emit({"status": "INPUT_ERROR", "error": "seal 需要 --expected-revision"}, 2)
            if args.session_json:
                session = _parse(args.session_json, "--session-json")
            else:
                session = store.load_snapshot()
            return _emit({"status": "OK", **store.seal_checkpoint(session, args.expected_revision)})

        if args.command == "append-usage":
            if not args.entry_json:
                return _emit({"status": "INPUT_ERROR", "error": "append-usage 需要 --entry-json"}, 2)
            store.append_usage(_parse(args.entry_json, "--entry-json"))
            return _emit({"status": "OK", "entries": len(store.read_usage())})

        if args.command == "read-usage":
            return _emit({"status": "OK", "entries": store.read_usage()})

    except CorruptEventLog as exc:
        return _emit({"status": "CORRUPT_EVENT_LOG", "error": str(exc), **exc.details}, 1)
    except RevisionConflict as exc:
        return _emit({"status": "REVISION_CONFLICT", "error": str(exc)}, 1)
    except ProjectionError as exc:
        return _emit({"status": "PROJECTION_ERROR", "error": str(exc)}, 1)
    except FileNotFoundError as exc:
        return _emit({"status": "NOT_FOUND", "error": str(exc)}, 2)
    except ValueError as exc:
        return _emit({"status": "INPUT_ERROR", "error": str(exc)}, 2)

    return _emit({"status": "INPUT_ERROR", "error": "未知命令"}, 2)


if __name__ == "__main__":
    sys.exit(main())
