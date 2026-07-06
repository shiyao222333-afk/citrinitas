# flake8: noqa: E501
"""Search Engine 分面统计 — 知识中枢仪表盘数据来源

从 search_engine.py 拆分（v1.0.2 代码质量清理）。
"""

import time
import requests
from collections import defaultdict

from qconst import QDRANT_URL, DEFAULT_COLLECTION, FACET_CACHE_TTL


def get_facet_stats(collection: str = DEFAULT_COLLECTION) -> dict:
    """
    获取知识库的分面维度统计。

    返回:
        {
            "ok": true,
            "total_points": N,
            "facets": {
                "content_type": {"knowledge": 120, "standard": 15, ...},
                "domain":        {"0": 45, "6": 30, ...},
                "temporal_nature": {"evergreen": 80, "timeboxed": 12, ...},
                "epistemic_status":{"corroborated": 50, "unverified": 30, ...},
            },
            "meta": {
                "avg_trust": 3.2,
                "personal_count": 5,
                "archived_count": 0,
            }
        }
    """
    from qconst import _check_qdrant

    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    # ── P1 fix: TTL 缓存，避免每次仪表盘刷新都全量 scroll ──
    _cache = getattr(get_facet_stats, "_cache", None)
    if _cache is not None and _cache.get("collection") == collection:
        cache_age = time.time() - _cache["ts"]
        if cache_age < FACET_CACHE_TTL:
            try:
                info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=3)
                if info.status_code == 200 and info.json()["result"]["points_count"] == _cache["pts"]:
                    return _cache["data"]
            except Exception:
                pass

    try:
        info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=5)
        if info.status_code != 200:
            return {"ok": False, "error": f"集合 {collection} 不存在"}

        total_pts = info.json()["result"]["points_count"]
        if total_pts == 0:
            result = {"ok": True, "total_points": 0, "facets": {}, "meta": {}}
            get_facet_stats._cache = {"ts": time.time(), "pts": 0, "collection": collection, "data": result}
            return result

        facets = {}
        meta_stats = {}

        # ── 分面分布统计 ──
        scroll_limit = 1000
        offset = 0
        ct_count = defaultdict(int)
        domain_count = defaultdict(int)
        tn_count = defaultdict(int)
        ep_count = defaultdict(int)
        trust_sum = 0
        trust_n = 0
        personal_n = 0
        archived_n = 0

        while offset < total_pts:
            try:
                resp = requests.post(
                    f"{QDRANT_URL}/collections/{collection}/points/scroll",
                    json={"limit": scroll_limit, "offset": offset,
                          "with_payload": True, "with_vector": False},
                    timeout=30
                )
                batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
                if not batch:
                    break
                for p in batch:
                    pl = p.get("payload", {})
                    ct = pl.get("content_type", "unknown")
                    ct_count[ct] += 1

                    for d in pl.get("domain", []):
                        domain_count[d] += 1

                    tn = pl.get("temporal_nature", "")
                    if tn:
                        tn_count[tn] += 1

                    ep = pl.get("epistemic_status", "")
                    if ep:
                        ep_count[ep] += 1

                    ts = pl.get("trust_score")
                    if ts is not None:
                        trust_sum += ts
                        trust_n += 1

                    if pl.get("is_personal", False):
                        personal_n += 1

                    if pl.get("is_archived", False):
                        archived_n += 1

                offset += len(batch)
            except Exception:
                break

        facets["content_type"] = dict(ct_count)
        facets["domain"] = dict(domain_count)
        facets["temporal_nature"] = dict(tn_count)
        facets["epistemic_status"] = dict(ep_count)

        meta_stats["avg_trust"] = round(trust_sum / trust_n, 1) if trust_n > 0 else 0
        meta_stats["personal_count"] = personal_n
        meta_stats["archived_count"] = archived_n

        result = {
            "ok": True,
            "total_points": total_pts,
            "facets": facets,
            "meta": meta_stats,
        }
        get_facet_stats._cache = {"ts": time.time(), "pts": total_pts, "collection": collection, "data": result}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}
