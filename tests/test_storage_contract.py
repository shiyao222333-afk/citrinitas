"""
Citrinitas 存储层契约测试（#35 根因治理，防回归）。

覆盖 #31 存储加固的全部风险点，使用内存假 Qdrant，无外部依赖、可直接运行：
    python tests/test_storage_contract.py

测试项（对应 PROJECT_PLAN 风险表）：
  R11  覆盖更新原子性：先写后删孤儿，写入失败不丢旧数据
  R12  删除失败显式报错（ok=False），不假装成功
  R13  统一 doc_id：新数据走 doc_id、旧数据走 doc_uid 兼容回退
  R14  update_document 用 set_payload，不动向量（混合检索不退化）
  R15  文档删除/重录清孤儿图，且删除限制在 IMAGES_DIR 内（防误删）
"""
import os
import sys
import tempfile

# ── 假 Qdrant（内存）──
STORE = []          # [{"id", "payload", "vector"}]
DELETE_FAIL = False # 测试 R12：让删除端点返回 500


def _match(payload, filt):
    for cond in filt.get("must", []):
        if payload.get(cond["key"]) != cond["match"]["value"]:
            return False
    return True


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload

    def json(self):
        return self._p


def _fake_post(url, json=None, timeout=30):
    j = json or {}
    if url.endswith("/points/scroll"):
        pts = [p for p in STORE if _match(p["payload"], j.get("filter", {}))]
        return _Resp(200, {"result": {"points": [
            {"id": p["id"], "payload": dict(p["payload"]), "vector": list(p["vector"])} for p in pts]}})
    if url.endswith("/points/delete"):
        if DELETE_FAIL:
            return _Resp(500, {"status": "error"})
        ids = set(j.get("points", []))
        before = len(STORE)
        STORE[:] = [p for p in STORE if p["id"] not in ids]
        return _Resp(200, {"result": {"status": "ok", "deleted": before - len(STORE)}})
    if url.endswith("/points/payload"):
        ids = set(j.get("points", []))
        for p in STORE:
            if p["id"] in ids:
                p["payload"].update(j.get("payload", {}))
        return _Resp(200, {"result": {"status": "ok"}})
    if url.endswith("/points"):
        for pt in j.get("points", []):
            STORE.append({"id": pt["id"], "payload": dict(pt["payload"]), "vector": list(pt.get("vector", []))})
        return _Resp(200, {"result": {"status": "ok"}})
    return _Resp(200, {"result": {}})


def _fake_get(url, timeout=5):
    return _Resp(200, {"result": {"status": "green", "points_count": len(STORE)}})


import requests as _r
_r.post = _fake_post
_r.get = _fake_get

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import doc_manager as dm
import storage_doctor as sd

TMP = tempfile.mkdtemp(prefix="cit_test_")
IMGDIR = os.path.join(TMP, "library", "images")
os.makedirs(os.path.join(IMGDIR, "books", "demo"))
dm.IMAGES_DIR = IMGDIR
dm.PROJECT_DIR = TMP

COL = "athanor_v1"
FAILS = []


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        FAILS.append(name)


def reset():
    STORE.clear()
    global DELETE_FAIL
    DELETE_FAIL = False


# ════════════════ R11：覆盖更新原子性（先写后删孤儿）══════════════
def test_r11_write_then_orphan():
    reset()
    # 模拟「旧文档 5 块」已存在
    for i in range(5):
        STORE.append({"id": ("doc", i), "payload": {"doc_id": "doc", "chunk_index": i, "text": f"old{i}"}, "vector": [0.1]})
    # 新写入 3 块（覆盖 0..2），keep_ids = 0..2
    keep = {("doc", i) for i in range(3)}
    res = dm.delete_orphan_points("doc", keep, collection=COL)
    check("R11 孤儿清理成功(删2留3)", res["ok"] and res["deleted"] == 2 and len(STORE) == 3)
    check("R11 保留块未被误删", all(p["payload"]["chunk_index"] in (0, 1, 2) for p in STORE))
    # keep_ids 为空时防御：绝不误删
    reset()
    STORE.append({"id": ("x", 0), "payload": {"doc_id": "x"}, "vector": [0.1]})
    res = dm.delete_orphan_points("x", set(), collection=COL)
    check("R11 keep_ids 空防御不删", res["ok"] and res["deleted"] == 0 and len(STORE) == 1)


# ════════════════ R12：删除失败显式报错 ═══════════════
def test_r12_delete_failure_reported():
    reset()
    STORE.append({"id": ("d", 0), "payload": {"doc_id": "d"}, "vector": [0.1]})
    STORE.append({"id": ("d", 1), "payload": {"doc_id": "d"}, "vector": [0.1]})
    global DELETE_FAIL
    DELETE_FAIL = True
    # keep_ids 非空且含 d0，使 d1 成为孤儿 → 触发删除端点（失败应显式报错）
    res = dm.delete_orphan_points("d", {("d", 0)}, collection=COL)
    check("R12 delete_orphan_points 失败返回 ok=False", (not res["ok"]) and "HTTP" in res.get("error", ""))
    # delete_points_by_doc_id 同样应该失败报错（不再静默 ok=True）
    reset()
    STORE.append({"id": ("d2", 0), "payload": {"doc_id": "d2"}, "vector": [0.1]})
    DELETE_FAIL = True
    res = dm.delete_points_by_doc_id("d2", collection=COL)
    check("R12 delete_points_by_doc_id 失败返回 ok=False", (not res["ok"]) and "HTTP" in res.get("error", ""))
    DELETE_FAIL = False


# ════════════════ R13：统一 doc_id（新数据 + 旧数据兼容）══════════════
def test_r13_doc_id_unification():
    reset()
    # 新数据：仅 doc_id
    STORE.append({"id": ("new", 0), "payload": {"doc_id": "new", "text": "a", "chunk_index": 0}, "vector": [0.1]})
    STORE.append({"id": ("new", 1), "payload": {"doc_id": "new", "text": "b", "chunk_index": 1}, "vector": [0.1]})
    r = dm.list_documents(collection=COL)
    check("R13 新数据 list 按 doc_id 发现", r["ok"] and len(r["documents"]) == 1 and r["documents"][0]["doc_id"] == "new")
    g = dm.get_document("new", collection=COL)
    check("R13 新数据 get 按 doc_id 命中", g["ok"] and len(g["chunks"]) == 2)
    d = dm.delete_document("new", collection=COL)
    check("R13 新数据 delete 按 doc_id", d["ok"] and d["deleted"] == 2 and len(STORE) == 0)

    reset()
    # 旧数据：仅 doc_uid（迁移前）
    STORE.append({"id": ("old", 0), "payload": {"doc_uid": "old", "text": "legacy", "chunk_index": 0}, "vector": [0.1]})
    r = dm.list_documents(collection=COL)
    check("R13 旧数据 list 兼容 doc_uid", r["ok"] and len(r["documents"]) == 1 and r["documents"][0]["doc_id"] == "old")
    g = dm.get_document("old", collection=COL)
    check("R13 旧数据 get 回退 doc_uid", g["ok"] and len(g["chunks"]) == 1)
    d = dm.delete_document("old", collection=COL)
    check("R13 旧数据 delete 回退 doc_uid", d["ok"] and d["deleted"] == 1 and len(STORE) == 0)

    # 删除不存在：报错而非静默成功
    reset()
    d = dm.delete_document("nope", collection=COL)
    check("R13 删除不存在报错", (not d["ok"]) and "不存在" in d.get("error", ""))


# ════════════════ R14：update_document 用 set_payload，不动向量 ═══════════════
def test_r14_update_preserves_vectors():
    reset()
    STORE.append({"id": ("u", 0), "payload": {"doc_id": "u", "text": "old", "trust_score": 3, "images": []}, "vector": [0.9, 0.8]})
    global _HITS
    _HITS = []
    _orig_post = _r.post

    def _tracking(url, json=None, timeout=30):
        _HITS.append(url)
        return _orig_post(url, json=json, timeout=timeout)
    _r.post = _tracking
    try:
        r = dm.update_document("u", {"trust_score": 5, "is_archived": True}, collection=COL)
    finally:
        _r.post = _orig_post
    check("R14 更新成功", r["ok"] and r["updated"] == 1)
    check("R14 走 set_payload 端点", any(u.endswith("/points/payload") for u in _HITS))
    check("R14 未走全量 PUT /points", not any(u.rstrip("/") == "http://example/collections/athanor_v1/points" for u in _HITS))
    pt = STORE[0]
    check("R14 向量保留(混合检索不退化)", pt["vector"] == [0.9, 0.8])
    check("R14 元数据 key-level 合并", pt["payload"].get("trust_score") == 5 and pt["payload"].get("is_archived") is True and pt["payload"].get("text") == "old")


# ════════════════ R15：删除文档/孤儿清图 + 删除护栏 ═══════════════
def test_r15_image_cleanup_with_guard():
    reset()
    img_in = "library/images/books/demo/a.png"
    img_out = os.path.join(TMP, "outside.png")  # IMAGES_DIR 外绝对路径，应保留
    with open(os.path.join(IMGDIR, "books", "demo", "a.png"), "wb") as f:
        f.write(b"x")
    with open(img_out, "wb") as f:
        f.write(b"y")
    STORE.append({"id": ("d1", 0), "payload": {"doc_id": "d1", "images": [img_in], "chunk_index": 0}, "vector": [0.1]})
    STORE.append({"id": ("d1", 1), "payload": {"doc_id": "d1", "images": [img_out], "chunk_index": 1}, "vector": [0.1]})
    r = dm.delete_document("d1", collection=COL)
    check("R15 删除成功", r["ok"] and r["deleted"] == 2)
    check("R15 IMAGES_DIR 内图被删", not os.path.isfile(os.path.join(IMGDIR, "books", "demo", "a.png")))
    check("R15 IMAGES_DIR 外图被护栏保留", os.path.isfile(img_out))
    check("R15 返回 images_cleaned>=1", r.get("images_cleaned", 0) >= 1)

    # 重录路径：delete_orphan_points 清孤儿图
    reset()
    orphan_img = "library/images/books/demo/old.png"
    with open(os.path.join(IMGDIR, "books", "demo", "old.png"), "wb") as f:
        f.write(b"z")
    STORE.append({"id": ("d3", 0), "payload": {"doc_id": "d3", "images": []}, "vector": [0.1]})
    STORE.append({"id": ("d3", 5), "payload": {"doc_id": "d3", "images": [orphan_img]}, "vector": [0.1]})
    r = dm.delete_orphan_points("d3", {("d3", 0)}, collection=COL)
    check("R15 孤儿块被删", r["ok"] and r["deleted"] == 1)
    check("R15 孤儿图被清", not os.path.isfile(os.path.join(IMGDIR, "books", "demo", "old.png")))


# ════════════════ 额外：update_metadata 用 set_payload（回归保护）══════════════
def test_update_metadata_safe():
    reset()
    STORE.append({"id": ("m", 0), "payload": {"doc_id": "m", "trust_score": 3}, "vector": [0.1]})
    r = dm.update_metadata("m", {"trust_score": 5}, collection=COL)
    check("update_metadata 成功", r["ok"] and r["updated"] == 1)
    check("update_metadata 生效且不动其它", STORE[0]["payload"].get("trust_score") == 5 and STORE[0]["payload"].get("doc_id") == "m")


# ════════════════ 存储医生：纯函数诊断（#35 工具自身回归）══════════════
def test_storage_doctor_classify():
    probs = sd.classify_point(("x", 0), {"text": "a"}, TMP)
    check("医生: 缺失 doc_id 被识别", "missing_doc_id" in probs)
    probs = sd.classify_point(("x", 1), {"doc_id": "a", "doc_uid": "b"}, TMP)
    check("医生: doc_uid 不一致被识别", "doc_uid_mismatch" in probs)
    probs = sd.classify_point(("x", 2), {"doc_id": "a", "doc_uid": "a"}, TMP)
    check("医生: doc_uid 一致无问题", "doc_uid_mismatch" not in probs)
    probs = sd.classify_point(("x", 3), {"doc_id": "a", "source_path": "library/images/books/demo/nope.txt"}, TMP)
    check("医生: 失效源文件被识别", "missing_source_file" in probs)
    probs = sd.classify_point(("x", 4), {"doc_id": "a", "images": ["library/images/books/demo/missing.png"]}, TMP)
    check("医生: 失效图片被识别", "missing_image_file" in probs)
    good_img = "library/images/books/demo/good.png"
    with open(os.path.join(IMGDIR, "books", "demo", "good.png"), "wb") as f:
        f.write(b"g")
    probs = sd.classify_point(("x", 5), {"doc_id": "a", "doc_uid": "a",
                                        "source_path": good_img, "images": [good_img]}, TMP)
    check("医生: 健康点无问题", probs == [])


if __name__ == "__main__":
    test_r11_write_then_orphan()
    test_r12_delete_failure_reported()
    test_r13_doc_id_unification()
    test_r14_update_preserves_vectors()
    test_r15_image_cleanup_with_guard()
    test_update_metadata_safe()
    test_storage_doctor_classify()
    print("\n==== 结果:", "ALL PASS ✅" if not FAILS else f"FAILURES ❌ {FAILS}")
    sys.exit(1 if FAILS else 0)
