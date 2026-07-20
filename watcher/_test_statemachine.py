"""Plan B 状态机定向测试（AI 设计决策，非用户指令）。

验证 #234-#240 的纯逻辑：不依赖 qdrant/ollama，只测状态文件驱动的去重/防重探测。
运行: venv/Scripts/python.exe watcher/_test_statemachine.py
"""
import os, sys, json, tempfile
from queue import Queue

sys.path.insert(0, r"D:\citrinitas")
import watcher.listener as L
import watcher.state as S
import watcher.utils as U

TMP = tempfile.mkdtemp(prefix="wtest_")
INBOX = os.path.join(TMP, "inbox")
os.makedirs(INBOX, exist_ok=True)
STATE = os.path.join(TMP, "file_state.jsonl")

# 重定向所有路径引用（三个模块都 from watcher.utils import，需逐个打补丁）
for mod in (L, S, U):
    mod.STATE_FILE = STATE
    mod.INBOX_DIR = INBOX
# 关闭 TTL 节流，让 _cleanup_expired_states 立即执行
L.WATCH_V2_CLEANUP_INTERVAL = 0
L.WATCH_V2_DLQ_TTL_DAYS = 1
# 救孤儿需要 infra_ok
L._watch_stats["infra_ok"] = True


def reset():
    open(STATE, "w", encoding="utf-8").close()
    for f in os.listdir(INBOX):
        os.remove(os.path.join(INBOX, f))
    while not L._queued_files._set if hasattr(L._queued_files, "_set") else False:
        break
    L._queued_files.clear()
    L._in_flight.clear()
    L._cleanup_expired_states._last_run = 0.0


def write_state(entries):
    with open(STATE, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def touch(*names):
    for n in names:
        with open(os.path.join(INBOX, n), "w", encoding="utf-8") as f:
            f.write("x")


def drain(q):
    got = []
    while not q.empty():
        got.append(os.path.basename(q.get_nowait()))
    return sorted(got)


def read_state():
    out = {}
    if os.path.isfile(STATE):
        with open(STATE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                out[e.get("file", "")] = e
    return out


# ── 测试 1：启动全扫只入队「无记录」新文件，retry/done/failed/processing 全跳 ──
reset()
touch("a.md", "b.md", "c.md", "d.md", "e.md")
write_state([
    {"file": "b.md", "state": "done"},
    {"file": "c.md", "state": "failed"},
    {"file": "d.md", "state": "retry"},
    {"file": "e.md", "state": "processing"},
])
q = Queue()
L._scan_existing_files(q)
got = drain(q)
assert got == ["a.md"], f"T1 失败: 期望只入队 a.md，实际 {got}"
print("T1 启动全扫 ✓ 只入队无记录文件:", got)

# ── 测试 2：周期救孤儿跳过 done/failed/processing，放行 retry + 无记录 ──
reset()
touch("a.md", "b.md", "c.md", "d.md", "e.md")
write_state([
    {"file": "b.md", "state": "done"},
    {"file": "c.md", "state": "failed"},
    {"file": "d.md", "state": "retry"},
    {"file": "e.md", "state": "processing"},
])
q = Queue()
L._rescue_orphaned_files(q)
got = drain(q)
assert got == ["a.md", "d.md"], f"T2 失败: 期望 [a.md,d.md]，实际 {got}"
print("T2 周期救孤儿 ✓ 放行 无记录+retry:", got)

# ── 测试 3：启动复位 processing → retry ──
reset()
touch("x.md")
write_state([{"file": "x.md", "state": "processing"}])
L._reset_processing_states()
st = read_state()
assert st["x.md"]["state"] == "retry", f"T3 失败: 期望 retry，实际 {st.get('x.md')}"
print("T3 启动复位 ✓ processing→retry:", st["x.md"]["state"])

# ── 测试 4：TTL 清理保留「终态且文件仍在 inbox」的记录，其余过期删除 ──
reset()
import time
from datetime import datetime, timezone, timedelta
old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
touch("keep.md", "oldretry.md", "fresh.md")  # gone.md 不在 inbox
write_state([
    {"file": "keep.md", "state": "done", "ts": old},        # 终态+文件在 → 保留
    {"file": "gone.md", "state": "done", "ts": old},        # 终态+文件不在 → 删除
    {"file": "oldretry.md", "state": "retry", "ts": old},   # 非终态 → 删除
    {"file": "fresh.md", "state": "done", "ts": datetime.now(timezone.utc).isoformat()},  # 未过期 → 保留
])
L._cleanup_expired_states()
st = read_state()
assert "keep.md" in st, "T4 失败: keep.md 应被保留"
assert "gone.md" not in st, "T4 失败: gone.md 应被删除"
assert "oldretry.md" not in st, "T4 失败: oldretry.md 应被删除"
assert "fresh.md" in st, "T4 失败: fresh.md 应被保留"
print("T4 TTL清理 ✓ 终态留inbox保留/其余过期删除:", sorted(st.keys()))

# ── 测试 5：主循环跳过集（防重探测核心规则）──
reset()
states = {}
for s in ("done", "failed", "needs_review", "processing", "pending"):
    touch(f"{s}.md")
    if s != "pending":
        states[f"{s}.md"] = s
write_state([{"file": k, "state": v} for k, v in states.items()])
# pending 应为无记录
cur = L._get_file_state("pending.md")
assert cur is None, "T5 失败: pending 应为无记录"
# 四个终态/处理中应被跳过
for s in ("done", "failed", "needs_review", "processing"):
    cur = L._get_file_state(f"{s}.md")
    assert cur.get("state") == s
    skip = cur.get("state") in ("done", "failed", "needs_review", "processing")
    assert skip, f"T5 失败: {s} 应被跳过"
# retry 应放行
write_state([{"file": "retry.md", "state": "retry"}])
touch("retry.md")
cur = L._get_file_state("retry.md")
assert cur.get("state") == "retry"
assert (cur.get("state") in ("done", "failed", "needs_review", "processing")) is False
print("T5 跳过集 ✓ 终态+processing跳过 / pending+retry放行")

print("\n全部状态机测试通过 ✅")
