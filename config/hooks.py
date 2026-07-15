"""
预存储钩子注册表 — Pre-Store Hook Registry

外部程序（如 Nigredo / Alembic）可通过 register_hook() 注册钩子函数，
在 Citrinitas 摄入管线的「嵌入完成→写入 Qdrant」阶段介入。

钩子函数签名:
    hook(state: dict) -> state: dict

state 包含:
    file_path, text, collection, metadata, model,
    source, content_hash, chunks, vectors, valid_images,
    doc_id, ingested_at, points

钩子可以修改 state 中的任意字段后返回。管线会使用修改后的 state 继续执行。

用法:
    from config.hooks import register_hook

    def my_hook(state):
        state["metadata"]["source_project"] = "nigredo"
        return state

    register_hook(my_hook)
"""

import json
from pathlib import Path

_hooks: list = []


def register_hook(hook):
    """注册一个预存储钩子函数"""
    if hook not in _hooks:
        _hooks.append(hook)


def get_hooks() -> list:
    """返回当前注册的所有钩子（副本，防止外部修改内部列表）"""
    return list(_hooks)


# ── Albedo 中转② 元数据钩子（ADR-005 兑现）────────────────────────────
# Albedo 把中转②写成 {name}_refined.md（报告）+ {name}_refined.meta.json（机读 ingestion_meta）。
# 熔知摄入 .md 时，此钩子在「嵌入完成→写 Qdrant」前读取同目录 sidecar，
# 把 ingestion_meta 合并进 payload（仅填空缺，不覆盖熔知自有分类 → 熔知保留最终裁决权）。

# Albedo ingestion_meta 字段 → Citrinitas payload 字段
_INGESTION_META_MAP = {
    "content_type": "content_type",
    "domain_udc_main": "domain",
    "domain_udc_code": "udc_code",
    "domain_label": "domain_label",
    "temporal_nature": "temporal_nature",
    "epistemic_status": "epistemic_status",
    "trust_score": "trust_score",
    "knowledge_type": "knowledge_type",
    "target_platform": "target_platform",
    "language": "language",
    "is_personal": "is_personal",
    "access_level": "access_level",
    "lifecycle": "lifecycle",
    "project_source": "project_source",
}

# 炼真权威字段：必须压过熔知朴素分类。
# 炼真是「质检关卡」，真实性裁决（epistemic_status / trust_score）归它；
# 此外内容类型 / 标题 / 作者 虽由熔知从文件来源(platform/frontmatter)确定性派生，
# 但按「馏析数据须经炼真才入熔知」原则，炼真在 ingestion_meta 声明时即为权威，强制覆盖。
# 炼真未声明（当前默认值）时 hook 跳过，熔知派生值照常生效，无回退。
_OVERRIDE_FIELDS = {"epistemic_status", "trust_score", "content_type", "title", "author"}


def albedo_meta_hook(state: dict) -> dict:
    """读取 Albedo 中转② sidecar，合并 ingestion_meta 进 state["metadata"]。

    无 sidecar（非 Albedo 产出）则原样返回，对其它摄入零影响。
    """
    fp = state.get("file_path") or ""
    if not fp:
        return state
    sidecar = Path(fp).with_suffix(".meta.json")
    if not sidecar.is_file():
        return state
    try:
        data = json.loads(Path(sidecar).read_text(encoding="utf-8"))
    except Exception:
        return state
    meta = data.get("ingestion_meta") or {}
    if not isinstance(meta, dict) or not meta:
        return state

    md = state.setdefault("metadata", {})
    for src_key, dst_key in _INGESTION_META_MAP.items():
        val = meta.get(src_key)
        if val is None or val == "" or val == []:
            continue
        if src_key in _OVERRIDE_FIELDS:
            # 炼真裁决优先：直接覆盖熔知朴素分类（把关不可被绕过）
            md[dst_key] = val
        else:
            # 仅填空缺：描述性分面熔知已算出的优先
            if dst_key not in md or md.get(dst_key) in (None, ""):
                md[dst_key] = val
    md["source_project"] = "albedo-refined"
    if data.get("status"):
        md["refined_status"] = data["status"]
    return state


# 模块加载即注册（ingest_service._step_pre_store_hooks 会在管线中调用 get_hooks）
register_hook(albedo_meta_hook)
