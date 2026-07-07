"""
Reranker Module — 重排序模块

使用嵌入模型对搜索结果进行重排序。
通过计算查询和文档的余弦相似度来重新排序结果。
"""

import numpy as np
from typing import List, Dict, Any
import os

# 配置
RERANKER_MODEL = os.environ.get("KB_RERANK_MODEL", "qwen3-embedding:4b")
OLLAMA_URL = "http://localhost:11434"


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    dot = np.dot(v1, v2)
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    return float(dot / norm) if norm > 0 else 0.0


def rerank_results(
    query: str,
    results: List[Dict[str, Any]],
    model: str = None,
    top_n: int = 20,
    ollama_url: str = None,
    query_vec: List[float] = None,
    doc_vectors: Dict = None
) -> List[Dict[str, Any]]:
    """
    使用嵌入模型对搜索结果重新打分排序。

    参数:
        query: 原始查询文本
        results: Qdrant 搜索结果列表（含 payload）
        model: 嵌入模型名称（用于计算相似度）
        top_n: 取前 N 个结果进行重排序
        ollama_url: Ollama API 地址
        query_vec: 搜索时已计算的 query 稠密向量（复用可省一次 Ollama 嵌入）
        doc_vectors: {point_id: 稠密向量} 映射（来自 Qdrant 已存向量，复用可省 N 次 Ollama 嵌入）

    返回:
        重排序后的结果列表（含原始 score 和 rerank_score）
    """
    if not results:
        return results

    # 使用环境变量或默认模型
    model = model or RERANKER_MODEL
    ollama_url = ollama_url or OLLAMA_URL

    # 取前 top_n 个结果
    candidates = results[:top_n]

    # ── 快速路径：复用已存向量（推荐）──
    # 搜索时已算出 query_vec，文档向量由 Qdrant 一并返回；直接用 numpy 算余弦，
    # 免去对 20 个候选段落再次调用 Ollama 嵌入（每次搜索省约 2~3 秒），
    # 且排序质量与原有 Ollama 路径等价（嵌入模型与入库时一致）。
    if query_vec is not None and doc_vectors is not None:
        rerank_scores = []
        for r in candidates:
            dv = doc_vectors.get(r.get("id"))
            rerank_scores.append(_cosine_similarity(query_vec, dv) if dv else 0.0)
        for i, r in enumerate(candidates):
            r["rerank_score"] = round(rerank_scores[i], 4)
        reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
        if len(results) > top_n:
            reranked.extend(results[top_n:])
        print("[Reranker] ✅ 重排序完成（复用已存向量，免 Ollama 重嵌入）")
        return reranked

    try:
        import requests
        
        # 准备输入：[query, doc1, doc2, ...]
        docs = [r.get("payload", {}).get("text", "") for r in candidates]
        input_texts = [query] + docs
        
        # 调用 Ollama embed API 获取向量
        resp = requests.post(
            f"{ollama_url}/api/embed",
            json={
                "model": model,
                "input": input_texts
            },
            timeout=60
        )
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
        
        if not embeddings or len(embeddings) < 2:
            print(f"[Reranker] 警告：未获取到有效嵌入，跳过重排序")
            return results
        
        # 第一个向量是 query，后面是 docs
        query_vec = embeddings[0]
        doc_vecs = embeddings[1:]
        
        # 计算余弦相似度作为重排序分数
        rerank_scores = []
        for doc_vec in doc_vecs:
            score = _cosine_similarity(query_vec, doc_vec)
            rerank_scores.append(score)
        
        # 将重排序分数附加到结果中
        for i, r in enumerate(candidates):
            r["rerank_score"] = round(rerank_scores[i], 4)
        
        # 按重排序分数降序排列
        reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
        
        # 后面的结果保持不变
        if len(results) > top_n:
            reranked.extend(results[top_n:])
        
        print(f"[Reranker] ✅ 重排序完成，使用模型: {model}")
        return reranked
        
    except Exception as e:
        print(f"[Reranker] 重排序失败：{e}，返回原始结果")
        return results


def rerank_results_simple(
    query: str,
    results: List[Dict[str, Any]],
    top_n: int = 20
) -> List[Dict[str, Any]]:
    """
    简单重排序（基于关键词匹配，不依赖 Ollama）。
    用于测试或 Ollama 未启动时。
    """
    if not results:
        return results
    
    candidates = results[:top_n]
    query_lower = query.lower()
    
    for r in candidates:
        text = r.get("payload", {}).get("text", "").lower()
        # 简单的关键词匹配分数
        query_words = set(query_lower.split())
        text_words = set(text.split())
        overlap = len(query_words & text_words)
        mock_score = overlap / len(query_words) if query_words else 0.0
        r["rerank_score"] = round(mock_score, 4)
    
    reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
    
    if len(results) > top_n:
        reranked.extend(results[top_n:])
    
    return reranked
