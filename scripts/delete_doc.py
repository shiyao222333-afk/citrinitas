"""验收辅助：删除某文档（清理测试数据）。

属于「巨作验收流程（OpusMagnum/acceptance）」调用的薄命令，不在正常摄入链路内。
直接复用 doc_manager.delete_document（删该 doc 全部分块 + 关联图片）。

用法:
    python scripts/delete_doc.py <doc_id> [--collection athanor_v1]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from doc_manager import delete_document  # noqa: E402
from qconst import DEFAULT_COLLECTION  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="删除文档（验收清理测试数据）")
    ap.add_argument("doc_id")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    args = ap.parse_args()

    res = delete_document(args.doc_id, args.collection)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
