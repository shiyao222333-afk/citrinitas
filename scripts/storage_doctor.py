"""
Citrinitas 存储医生（#35 根因治理）— 知识库体检 + 可选修复。

默认只读扫描，打印问题汇总；显式加 --fix <项目> 才动手。

扫描项：
  missing_doc_id       point 缺少 doc_id（写入异常遗留，无法按文档管理）
  doc_uid_mismatch     doc_uid 存在但与 doc_id 不一致（R13 残留双身份）
  missing_source_file  顶层/source_path 或 origin.source_path 指向的源文件在磁盘不存在
  missing_image_file   images 引用的图片在磁盘不存在（R15 孤儿图）
  duplicate_point_id   重复 point_id（确定性 id 碰撞或重复写入）

用法：
  python scripts/storage_doctor.py                 # 只读报告
  python scripts/storage_doctor.py --fix doc-uid-mismatch
  python scripts/storage_doctor.py --fix prune-images
  python scripts/storage_doctor.py --fix missing-doc-id   # 危险：删除无 doc_id 的点
  python scripts/storage_doctor.py --collection athanor_v1 --limit 50000
"""
import os
import sys
import json
import argparse
import requests

try:
    from qconst import QDRANT_URL, DEFAULT_COLLECTION, PROJECT_DIR
except Exception as e:
    print(f"❌ 无法导入 qconst（请在项目根目录运行）: {e}")
    sys.exit(1)


# ═══════════════════════════════════════════
# 纯函数：单点诊断（便于单测，不触网）
# ═════════════════════════════════════════
def classify_point(pid, payload: dict, project_dir: str) -> list:
    """返回该 point 的问题码列表。"""
    problems = []
    doc_id = payload.get("doc_id")
    if not doc_id:
        problems.append("missing_doc_id")
    doc_uid = payload.get("doc_uid")
    if doc_uid and doc_id and doc_uid != doc_id:
        problems.append("doc_uid_mismatch")

    # 源文件存在性
    src = payload.get("source_path") or (payload.get("origin") or {}).get("source_path")
    if src:
        p = src if os.path.isabs(src) else os.path.join(project_dir, src)
        if not os.path.isfile(p):
            problems.append("missing_source_file")

    # 图片存在性
    for img in (payload.get("images") or []):
        if not isinstance(img, str) or not img:
            continue
        p = img if os.path.isabs(img) else os.path.join(project_dir, img)
        if not os.path.isfile(p):
            problems.append("missing_image_file")
            break  # 一个点只报一次图片缺失
    return problems


# ═══════════════════════════════════════════
# 扫描
# ═════════════════════════════════════════
def collect_points(collection: str, limit: int = 50000):
    points = []
    offset = 0
    batch = 1000
    seen_ids = {}
    dup = 0
    while len(points) < limit:
        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json={"limit": batch, "offset": offset,
                  "with_payload": True, "with_vector": False},
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"❌ scroll 失败 HTTP {resp.status_code}")
            break
        page = resp.json()["result"]["points"]
        if not page:
            break
        for p in page:
            pid = p["id"]
            if pid in seen_ids:
                dup += 1
            else:
                seen_ids[pid] = True
                points.append(p)
        offset += len(page)
        if len(page) < batch:
            break
    return points, dup


def scan(collection: str, project_dir: str, limit: int = 50000):
    print(f"🔍 扫描集合 {collection} ...")
    points, dup = collect_points(collection, limit)
    total = len(points)
    print(f"   共 {total} 个 point，{dup} 个重复 id")

    counts = {}
    samples = {k: [] for k in ("missing_doc_id", "doc_uid_mismatch",
                               "missing_source_file", "missing_image_file")}
    for p in points:
        for code in classify_point(p["id"], p.get("payload", {}), project_dir):
            counts[code] = counts.get(code, 0) + 1
            if len(samples[code]) < 5:
                samples[code].append(p["id"])

    print("\n==== 存储体检报告 ====")
    print(f"总 point 数      : {total}")
    print(f"重复 point_id    : {dup}")
    for code in ("missing_doc_id", "doc_uid_mismatch", "missing_source_file", "missing_image_file"):
        n = counts.get(code, 0)
        flag = "⚠️" if n else "✅"
        print(f"{flag} {code:<20}: {n}")
        for sid in samples[code]:
            print(f"      · {sid}")
    print("======================")
    return counts, dup


# ═══════════════════════════════════════════
# 修复
# ═════════════════════════════════════════
def fix_doc_uid_mismatch(collection: str):
    points, _ = collect_points(collection, 50000)
    targets = [(p["id"], p["payload"]["doc_id"])
               for p in points
               if p.get("payload", {}).get("doc_uid") and p["payload"].get("doc_id")
               and p["payload"]["doc_uid"] != p["payload"]["doc_id"]]
    if not targets:
        print("✅ 无 doc_uid 不一致的点")
        return
    print(f"🔧 归一化 {len(targets)} 个点的 doc_uid=doc_id ...")
    for pid, doc_id in targets:
        requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/payload",
            json={"payload": {"doc_uid": doc_id}, "points": [pid]},
            timeout=10,
        )
    print(f"   完成 {len(targets)} 个")


def fix_prune_images(collection: str, project_dir: str):
    points, _ = collect_points(collection, 50000)
    fixed = 0
    for p in points:
        imgs = p.get("payload", {}).get("images") or []
        kept = []
        changed = False
        for img in imgs:
            path = img if os.path.isabs(img) else os.path.join(project_dir, img)
            if os.path.isfile(path):
                kept.append(img)
            else:
                changed = True
        if changed:
            requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/payload",
                json={"payload": {"images": kept}, "points": [p["id"]]},
                timeout=10,
            )
            fixed += 1
    print(f"🔧 清理 {fixed} 个点的失效图片引用")


def fix_missing_doc_id(collection: str):
    points, _ = collect_points(collection, 50000)
    bad = [p["id"] for p in points if not p.get("payload", {}).get("doc_id")]
    if not bad:
        print("✅ 无缺失 doc_id 的点")
        return
    print(f"🔧 删除 {len(bad)} 个缺失 doc_id 的孤儿点 ...")
    for i in range(0, len(bad), 1000):
        requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/delete",
            json={"points": bad[i:i + 1000]},
            timeout=30,
        )
    print(f"   完成 {len(bad)} 个")


def main():
    ap = argparse.ArgumentParser(description="Citrinitas 存储医生")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--limit", type=int, default=50000)
    ap.add_argument("--fix", nargs="*", default=[],
                    choices=["doc-uid-mismatch", "prune-images", "missing-doc-id"],
                    help="显式修复项（默认不修，只读）")
    args = ap.parse_args()

    # 连通性
    try:
        r = requests.get(f"{QDRANT_URL}/collections/{args.collection}", timeout=5)
        if r.status_code != 200:
            print(f"❌ 集合 {args.collection} 不可达 (HTTP {r.status_code})")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 无法连接 Qdrant ({QDRANT_URL}): {e}")
        sys.exit(1)

    counts, _ = scan(args.collection, PROJECT_DIR, args.limit)

    if not args.fix:
        print("\n（只读模式。需要修复请加 --fix <项目>，例如 --fix doc-uid-mismatch）")
        return

    for item in args.fix:
        if item == "doc-uid-mismatch":
            fix_doc_uid_mismatch(args.collection)
        elif item == "prune-images":
            fix_prune_images(args.collection, PROJECT_DIR)
        elif item == "missing-doc-id":
            print("⚠️ 即将删除缺失 doc_id 的孤儿点（不可撤销）")
            fix_missing_doc_id(args.collection)
    print("\n✅ 修复完成。建议再跑一次不带 --fix 复核。")


if __name__ == "__main__":
    main()
