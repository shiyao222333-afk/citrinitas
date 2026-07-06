"""
Sparse Encoder Module — 稀疏向量生成器

为 Qdrant 混合查询生成 BM25 稀疏向量。
配置：sparse_vectors = {"bm25": {"modifier": "idf"}}
摄入时只需提供词频（TF），Qdrant 自动计算 IDF。

并发安全：词汇表是进程内全局状态，摄入可能在多个线程同时进行
（守望线程 + 网页上传线程），因此对词典的读写与落盘都用锁保护，
且落盘采用原子写（临时文件 + os.replace），避免并发损坏。
"""

import json
import os
import re
import threading

import jieba

# 全局词汇表：token → index
_SPARSE_VOCAB = {}
_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "sparse_vocab.json")
_MAX_VOCAB_SIZE = 50000  # 最大词汇表大小
_VOCAB_LOCK = threading.Lock()  # 并发保护：摄入可能多线程同时进行


def _load_vocab():
    """加载词汇表（调用方需持有 _VOCAB_LOCK）"""
    global _SPARSE_VOCAB
    if os.path.exists(_VOCAB_PATH):
        try:
            with open(_VOCAB_PATH, "r", encoding="utf-8") as f:
                _SPARSE_VOCAB = json.load(f)
        except Exception:
            _SPARSE_VOCAB = {}
    else:
        _SPARSE_VOCAB = {}


def _save_vocab():
    """保存词汇表（调用方需持有 _VOCAB_LOCK；原子写避免并发损坏）"""
    tmp_path = _VOCAB_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_SPARSE_VOCAB, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, _VOCAB_PATH)


def flush_vocab():
    """将累积的新词一次性落盘（批量摄入结束后调用，避免每块都重写整个文件）"""
    with _VOCAB_LOCK:
        _save_vocab()


def tokenize(text: str) -> list:
    """中英文分词"""
    # 英文：按空格和标点分割
    en_tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    # 中文：使用 jieba 分词
    try:
        zh_tokens = list(jieba.cut_for_search(text))
        zh_tokens = [t.strip() for t in zh_tokens if t.strip()]
    except Exception:
        zh_tokens = []
    return en_tokens + zh_tokens


def encode_sparse(text: str, update_vocab: bool = True) -> tuple:
    """
    将文本编码为稀疏向量（用于摄入）。

    参数:
        text: 输入文本
        update_vocab: 是否将新词写入内存词典（批量摄入请设 False，结束显式调用 flush_vocab 落盘）

    返回:
        (indices, values) 元组
        - indices: 词 ID 列表（int）
        - values: 词频（TF）列表（float）
    """
    with _VOCAB_LOCK:
        if not _SPARSE_VOCAB:
            _load_vocab()

        tokens = tokenize(text)
        if not tokens:
            return [], []

        # 统计词频
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        indices = []
        values = []

        for token, count in tf.items():
            # 获取或分配 token index
            if token not in _SPARSE_VOCAB:
                if len(_SPARSE_VOCAB) >= _MAX_VOCAB_SIZE:
                    continue  # 跳过，词汇表已满
                _SPARSE_VOCAB[token] = len(_SPARSE_VOCAB)

            indices.append(_SPARSE_VOCAB[token])
            values.append(float(count))

        if update_vocab:
            _save_vocab()

    return indices, values


def encode_sparse_query(text: str) -> tuple:
    """
    将查询文本编码为稀疏向量（用于查询）。

    注意：查询时不能更新词汇表，只能使用已有的 token。
    """
    with _VOCAB_LOCK:
        if not _SPARSE_VOCAB:
            _load_vocab()

        tokens = tokenize(text)
        if not tokens:
            return [], []

        # 统计词频
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        indices = []
        values = []

        for token, count in tf.items():
            if token not in _SPARSE_VOCAB:
                continue  # 跳过词汇表中没有的词
            indices.append(_SPARSE_VOCAB[token])
            values.append(float(count))

    return indices, values


def get_vocab_size() -> int:
    """获取词汇表大小"""
    with _VOCAB_LOCK:
        if not _SPARSE_VOCAB:
            _load_vocab()
        return len(_SPARSE_VOCAB)


# 初始化时加载词汇表
_load_vocab()
