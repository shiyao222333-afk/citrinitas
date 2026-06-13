#!/usr/bin/env python3
"""
sync_ima.py — IMA 知识库 → KnowledgeForge 同步脚本

功能：
  1. 通过 IMA MCP 连接器读取知识库内容
  2. 将内容转换为 kb_query.py 可摄入的格式
  3. 自动调用摄入流程，写入本地 Qdrant

使用方式：
  # 同步整个知识库（需要 WorkBuddy 环境中运行，IMA MCP 已连接）
  python sync_ima.py --all

  # 同步指定知识库
  python sync_ima.py --kb-id 001a3e2517800730

  # 同步后自动搜索验证
  python sync_ima.py --all --verify

  # 只导出为 .txt 文件，不摄入（用于调试）
  python sync_ima.py --all --export-only --output ./ima_export/

架构说明：
  - 导入/导出不是自动的，需要主动运行此脚本
  - 可以扩展对接其他知识库（Notion、Obsidian、语雀等）
  - 扩展方法：新增一个 connector 类，实现 fetch() 和 convert() 方法
"""

import os
import sys
import json
import time
import argparse
import subprocess
import re
from pathlib import Path

# ─────────────────────────────────────────
# 配置
# ─────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
KB_QUERY_PY = SCRIPT_DIR / "kb_query.py"
LOCAL_DATA_DIR = SCRIPT_DIR / "local_data"
SUPPORTED_EXT = {".txt", ".md", ".docx", ".pdf"}  # 可扩展

# ─────────────────────────────────────────
# 核心类：IMA 连接器
# ─────────────────────────────────────────

class IMABConnector:
    """
    IMA 知识库连接器。

    注意：此类设计为在 WorkBuddy 环境中通过 MCP 工具调用。
    如果在纯 Python 环境中运行，需要手动提供 IMA API Token，
    或通过文件导入（--export-only 模式）。

    MCP 工具依赖（由 WorkBuddy 提供）：
      - mcp__ima-mcp__get_knowledge_base_list
      - mcp__ima-mcp__get_knowledge_list
      - mcp__ima-mcp__search_knowledge
      - mcp__ima-mcp__fetch_media_content
    """

    def __init__(self, mcp_call_fn=None):
        """
        Args:
            mcp_call_fn: MCP 工具调用函数（由 WorkBuddy 注入）
                        签名：mcp_call_fn(tool_name: str, params: dict) -> dict
        """
        self.call_mcp = mcp_call_fn

    def get_knowledge_bases(self):
        """获取知识库列表"""
        if self.call_mcp:
            result = self.call_mcp("mcp__ima-mcp__get_knowledge_base_list", {
                "params": [{"limit": 20, "type": "KBT_MINE_KB"}]
            })
            return result.get("results", {}).get("knowledge_base_list", [])
        else:
            # 非 WorkBuddy 环境：返回空列表，提示用户使用 --import-dir 模式
            print("⚠ IMA MCP 不可用，请使用 --import-dir 指定已导出的文件目录")
            return []

    def get_knowledge_items(self, kb_id, limit=100):
        """获取知识库中的条目列表"""
        if self.call_mcp:
            result = self.call_mcp("mcp__ima-mcp__get_knowledge_list", {
                "knowledge_base_id": kb_id,
                "cursor": "",
                "limit": limit,
            })
            info = result.get("results", {})
            return info.get("knowledge_list", []), info.get("is_end", True)
        return [], True

    def fetch_item_content(self, media_id):
        """获取单个知识条目的内容"""
        if self.call_mcp:
            result = self.call_mcp("mcp__ima-mcp__fetch_media_content", {
                "media_id": media_id,
            })
            return result.get("results", {})
        return {}

    def search_knowledge(self, kb_id, query, limit=20):
        """在知识库中搜索"""
        if self.call_mcp:
            result = self.call_mcp("mcp__ima-mcp__search_knowledge", {
                "knowledge_base_id": kb_id,
                "query": query,
                "cursor": "",
            })
            info = result.get("results", {})
            return info.get("searched_knowledge_list", [])
        return []


# ─────────────────────────────────────────
# 内容转换器
# ─────────────────────────────────────────

class ContentConverter:
    """将 IMA 知识库内容转换为 KnowledgeForge 可摄入的格式"""

    @staticmethod
    def media_type_to_ext(media_type):
        """将 IMA media_type 转换为文件扩展名"""
        mapping = {
            1: ".pdf",
            2: ".html",
            3: ".docx",
            4: ".pptx",
            5: ".xlsx",
            6: ".html",   # WECHAT_ARTICLE
            7: ".md",
            8: ".jpg",   # IMG
            9: ".md",     # NOTE
            10: ".txt",   # SESSION
            11: ".txt",
            12: ".xmind",
            13: ".mp3",  # SOUND_RECORDING
            14: ".mp4",  # WEB_VIDEO
            15: ".mp3",   # PODCAST
        }
        return mapping.get(media_type, ".txt")

    @staticmethod
    def convert_to_text(content_data, title=""):
        """
        将 IMA 内容转换为纯文本。
        支持：Markdown、纯文本、Word（需要 python-docx）
        """
        media_type = content_data.get("media_type", 0)
        raw_content = content_data.get("content", "")

        # Markdown / 纯文本：直接返回
        if media_type in (7, 9, 10, 11):  # MARKDOWN, NOTE, SESSION, TXT
            return raw_content

        # PDF / Word：content 可能是 base64 或需要 OCR
        # 这里输出为 .txt 文件，交给 kb_query.py 的 --ingest 处理
        if media_type in (1, 3):
            # 尝试提取纯文本
            text = ContentConverter._extract_text_from_html(raw_content)
            return text if text else raw_content

        # 图片：返回提示，需要 OCR
        if media_type == 8:
            return f"[图片内容，需要 OCR 处理]\n标题: {title}\n"

        return raw_content

    @staticmethod
    def _extract_text_from_html(html_content):
        """简单的 HTML 标签去除，提取纯文本"""
        if not html_content:
            return ""
        text = re.sub(r'<[^>]+>', ' ', html_content)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def save_as_file(content, title, output_dir, ext=".txt"):
        """将内容保存为文件"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 安全文件名
        safe_title = re.sub(r'[\\/*?:"<>|]', '_', title)[:100]
        file_path = output_dir / f"{safe_title}{ext}"

        # 去重（同名文件加序号）
        counter = 1
        while file_path.exists():
            file_path = output_dir / f"{safe_title}_{counter}{ext}"
            counter += 1

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return str(file_path)


# ─────────────────────────────────────────
# 摄入器
# ─────────────────────────────────────────

class Ingestor:
    """调用 kb_query.py 将文件摄入到 KnowledgeForge"""

    def __init__(self, kb_query_path, ocr_engine="paddle"):
        self.kb_query = Path(kb_query_path)
        self.ocr_engine = ocr_engine

    def ingest_text_file(self, file_path, source=None):
        """摄入文本文件"""
        cmd = [
            sys.executable, str(self.kb_query),
            "--ingest", str(file_path),
        ]
        if source:
            cmd.extend(["--source", source])

        print(f"  📥 摄入: {Path(file_path).name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ❌ 摄入失败: {result.stderr[:200]}")
            return False
        return True

    def ingest_image(self, image_path, source=None):
        """OCR 图片并摄入"""
        cmd = [
            sys.executable, str(self.kb_query),
            "--ocr", str(image_path),
            "--engine", self.ocr_engine,
        ]
        if source:
            cmd.extend(["--source", source])

        print(f"  🖼️  OCR摄入: {Path(image_path).name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ❌ OCR失败: {result.stderr[:200]}")
            return False
        return True

    def ingest_directory(self, dir_path, recursive=True):
        """批量摄入目录下的所有文件"""
        dir_path = Path(dir_path)
        pattern = "**/*" if recursive else "*"

        success, failed = 0, 0
        for file_path in dir_path.glob(pattern):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXT:
                continue

            if self.ingest_text_file(str(file_path), source=file_path.stem):
                success += 1
            else:
                failed += 1

        print(f"\n📊 批量摄入完成: 成功 {success}，失败 {failed}")
        return success, failed


# ─────────────────────────────────────────
# 主同步逻辑
# ─────────────────────────────────────────

def sync_via_mcp(connector, ingestor, kb_id=None, verify=False):
    """
    通过 MCP 工具同步 IMA 知识库。
    需要在 WorkBuddy 环境中运行（IMA MCP 已连接）。
    """
    print("🔗 通过 MCP 同步 IMA 知识库...\n")

    # 获取知识库列表
    kbs = connector.get_knowledge_bases()
    if not kbs:
        print("⚠ 未找到知识库，或 IMA MCP 不可用")
        print("   请确认：WorkBuddy 中 IMA 连接器已启用")
        return

    print(f"📚 找到 {len(kbs)} 个知识库:")
    for kb in kbs:
        info = kb.get("basic_info", {})
        print(f"   - {info.get('name', '未知')} (id: {kb.get('id', '?')})")

    # 确定要同步的知识库
    target_kbs = [kb for kb in kbs if not kb_id or kb.get("id") == kb_id]
    if not target_kbs:
        print(f"⚠ 未找到 id={kb_id} 的知识库")
        return

    # 遍历知识库
    total_ingested = 0
    for kb in target_kbs:
        kb_id = kb.get("id")
        kb_name = kb.get("basic_info", {}).get("name", "未知")
        print(f"\n📖 同步知识库: {kb_name}")

        # 获取条目
        items, is_end = connector.get_knowledge_items(kb_id, limit=100)
        print(f"   找到 {len(items)} 个条目")

        for item in items:
            title = item.get("title", "未知")
            media_id = item.get("media_id", "")
            media_type = item.get("media_type", 0)

            print(f"   📄 {title} (type={media_type})")

            # 获取内容
            content_data = connector.fetch_item_content(media_id)
            if not content_data:
                print(f"      ⚠ 获取内容失败，跳过")
                continue

            # 转换为文本
            text = ContentConverter.convert_to_text(content_data, title=title)
            if not text.strip():
                print(f"      ⚠ 内容为空，跳过")
                continue

            # 保存为临时文件并摄入
            tmp_file = ContentConverter.save_as_file(
                text, title,
                output_dir=SCRIPT_DIR / "ima_cache",
                ext=".txt"
            )
            if ingestor.ingest_text_file(tmp_file, source=kb_name):
                total_ingested += 1

            # 限速：避免 API 频率限制
            time.sleep(0.5)

    print(f"\n✅ 同步完成！共摄入 {total_ingested} 个条目")


def sync_via_import_dir(ingestor, import_dir):
    """
    通过已导出的文件目录同步。
    这是非 WorkBuddy 环境下的主要使用方式。
    IMA 知识库 → 导出为 .txt/.md/.docx → 放到一个目录 → 运行此脚本
    """
    import_dir = Path(import_dir)
    if not import_dir.is_dir():
        print(f"❌ 目录不存在: {import_dir}")
        return

    print(f"📁 从目录同步: {import_dir}\n")
    ingestor.ingest_directory(str(import_dir), recursive=True)


def verify_ingestion(query="测试", top_k=3):
    """验证摄入结果：运行一次搜索"""
    print(f"\n🔍 验证搜索（查询: {query}）...")
    cmd = [sys.executable, str(KB_QUERY_PY), query, "--top", str(top_k)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("⚠ 错误输出:", result.stderr[:300])


# ─────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="IMA 知识库 → KnowledgeForge 同步脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 通过 MCP 同步所有知识库（需要 WorkBuddy 环境）
  python sync_ima.py --all

  # 同步指定知识库
  python sync_ima.py --kb-id 001a3e2517800730

  # 从已导出的文件目录同步（通用方式）
  python sync_ima.py --import-dir ./ima_export/

  # 同步后验证
  python sync_ima.py --all --verify

扩展:
  要连接其他知识库（Notion/Obsidian/语雀），
  请参考 sync_ima.py 中的 Connector 类，实现对应的 fetch() 方法。
        """
    )

    parser.add_argument("--all", action="store_true",
                        help="同步所有 IMA 知识库（需要 MCP 环境）")
    parser.add_argument("--kb-id", type=str, default=None,
                        help="指定要同步的知识库 ID")
    parser.add_argument("--import-dir", type=str, default=None,
                        help="从已导出的文件目录同步（非 MCP 环境使用）")
    parser.add_argument("--export-only", action="store_true",
                        help="只导出为 .txt 文件，不摄入")
    parser.add_argument("--output", type=str, default="./ima_export/",
                        help="导出目录（配合 --export-only 使用）")
    parser.add_argument("--verify", action="store_true",
                        help="同步完成后运行一次搜索验证")
    parser.add_argument("--ocr-engine", type=str, default="paddle",
                        choices=["paddle", "tesseract", "structured"],
                        help="OCR 引擎（图片文件时使用）")

    args = parser.parse_args()

    # 检查 kb_query.py 是否存在
    if not KB_QUERY_PY.exists():
        print(f"❌ 找不到 kb_query.py: {KB_QUERY_PY}")
        sys.exit(1)

    ingestor = Ingestor(KB_QUERY_PY, ocr_engine=args.ocr_engine)

    # ── 模式 1：从导出目录同步 ──
    if args.import_dir:
        sync_via_import_dir(ingestor, args.import_dir)
        if args.verify:
            verify_ingestion()
        return

    # ── 模式 2：通过 MCP 同步 ──
    if args.all or args.kb_id:
        # 注意：MCP 工具需要在 WorkBuddy 环境中可用
        # 这里创建一个占位 connector，实际调用需要通过 WorkBuddy
        print("⚠ 注意：通过 MCP 同步需要在 WorkBuddy 环境中运行")
        print("   如果你在命令行直接运行，请使用 --import-dir 模式\n")

        # 尝试检查是否可以通过环境变量获取 IMA token
        ima_token = os.environ.get("IMA_TOKEN")
        if ima_token:
            print("✅ 找到 IMA_TOKEN 环境变量，尝试直接 API 同步...")
            # TODO: 实现直接 API 调用（需要逆向 IMA API）
            print("⚠ 直接 API 同步尚未实现，请使用 --import-dir 模式")
        else:
            print("💡 使用方法：")
            print("   1. 在 IMA 知识库页面导出内容为 .txt/.md 文件")
            print("   2. 运行: python sync_ima.py --import-dir <导出目录>")
        return

    # ── 没有参数：显示帮助 ──
    parser.print_help()


if __name__ == "__main__":
    main()
