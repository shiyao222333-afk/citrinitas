"""验收辅助：导出某文档在 Qdrant 中的全部顶层 payload 字段（即「53 字段结果」）。

属于「巨作验收流程（OpusMagnum/acceptance）」调用的薄命令，不在正常摄入链路内。
原理：用 Qdrant REST scroll 按 doc_id（兼容旧 doc_uid）过滤，取首个分块 payload 全字段。
注意：直接 dump 真实值，不手抄字段清单——保证与 Qdrant 实际存储一致。

用法:
    python scripts/get_fields.py <doc_id> [--collection athanor_v1] [--out result.json]
输出: JSON（stdout + 可选写文件），含 doc_id / collection / n_points / field_count / fields。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qconst import QDRANT_URL, DEFAULT_COLLECTION  # noqa: E402
import requests  # noqa: E402


def get_fields(doc_id: str, collection: str = DEFAULT_COLLECTION) -> dict | None:
    """返回该 doc 首个分块 payload 的全部顶层字段（即 53 字段结果）。"""
    for key in ("doc_id", "doc_uid"):
        try:
            r = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={
                    "filter": {"must": [{"key": key, "match": {"value": doc_id}}]},
                    "with_payload": True,
                    "with_vector": False,
                    "limit": 20,
                },
                timeout=30,
            )
        except Exception as e:
            print(f"[warn] 查询 {key} 失败: {e}", file=sys.stderr)
            continue
        if r.status_code == 200:
            points = r.json().get("result", {}).get("points", [])
            if points:
                payload = points[0].get("payload", {})
                return {
                    "doc_id": doc_id,
                    "collection": collection,
                    "n_points": len(points),
                    "field_count": len(payload),
                    "fields": payload,
                }
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="导出文档全部顶层字段（53 字段结果）")
    ap.add_argument("doc_id")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--out", default=None, help="写文件路径（否则仅 stdout）")
    args = ap.parse_args()

    res = get_fields(args.doc_id, args.collection)
    if res is None:
        print(json.dumps({"ok": False, "error": f"文档 {args.doc_id} 未找到"}, ensure_ascii=False, indent=2))
        return 1

    text = json.dumps(res, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入: {args.out}（顶层字段数={res['field_count']}，分块数={res['n_points']}）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
