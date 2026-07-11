"""
轻量 EPUB 读取器（零第三方授权依赖，纯标准库实现）。

替代 AGPL 许可的 ebooklib。EPUB 本质是 ZIP 包：
  - META-INF/container.xml 指向 OPF 包文档（内容文件）
  - OPF 文件含 <metadata>（Dublin Core 等）与 <manifest>（资源清单）
  - manifest 项的 media-type 决定它是文档（XHTML/HTML）还是图片

对外暴露与 ebooklib 兼容的最小接口，便于平替：
  read_epub(path) -> EpubBook
  ITEM_DOCUMENT / ITEM_IMAGE 常量
  book.get_items_of_type(kind) -> 可迭代，每项有 .file_name / .get_content()
  book.get_metadata("DC", name) -> [(value, attrs), ...]
"""

import os
import zipfile
import posixpath
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# 与 ebooklib 对齐的常量（当前仅用到这两个类型）
ITEM_DOCUMENT = "application/xhtml+xml"
ITEM_IMAGE = "image"


class _EpubItem:
    """兼容 ebooklib 的单个资源项。"""

    def __init__(self, file_name: str, media_type: str, content: bytes):
        self.file_name = file_name      # manifest 中的 href（相对包根）
        self.media_type = media_type
        self._content = content

    def get_content(self) -> bytes:
        return self._content

    def get_name(self) -> str:
        return self.file_name


class EpubBook:
    """兼容 ebooklib.EpubBook 的最小实现。"""

    def __init__(self):
        self._items = []                 # list[_EpubItem]
        self._metadata = {}              # {"DC": {name: [(value, attrs), ...]}}
        self._opf_dir = ""

    def get_items(self):
        return list(self._items)

    def get_items_of_type(self, item_type):
        """按 media-type 过滤。item_type 取 ITEM_DOCUMENT / ITEM_IMAGE。"""
        for it in self._items:
            if item_type == ITEM_IMAGE and it.media_type.startswith("image/"):
                yield it
            elif item_type == ITEM_DOCUMENT and it.media_type in (
                "application/xhtml+xml", "application/html+xml", "text/html",
            ):
                yield it

    def get_metadata(self, namespace: str, name: str):
        """
        返回 [(value, attrs), ...]。
        namespace 传 "DC"（Dublin Core）；name 为 dc 元素本地名（title/creator/...）。
        """
        return self._metadata.get(namespace, {}).get(name, [])


def _local_name(tag: str) -> str:
    """从 {uri}local 或 local 中取出本地名（忽略命名空间）。"""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_container(zf: zipfile.ZipFile) -> str | None:
    """从 META-INF/container.xml 找到 OPF 包文档路径。"""
    try:
        data = zf.read("META-INF/container.xml")
    except KeyError:
        # 退化策略：找第一个 .opf
        for n in zf.namelist():
            if n.lower().endswith(".opf"):
                return n
        return None
    root = ET.fromstring(data)
    for el in root.iter():
        if _local_name(el.tag) == "rootfile":
            full = el.attrib.get("full-path")
            if full:
                return full
    return None


def _resolve(zf: zipfile.ZipFile, opf_dir: str, href: str) -> bytes | None:
    """把 manifest href 解析为 zip 内真实路径并读取内容。"""
    norm = posixpath.normpath(posixpath.join(opf_dir, href))
    try:
        return zf.read(norm)
    except KeyError:
        # 容忍 URL 编码 / 反斜杠差异
        try:
            return zf.read(norm.replace("\\", "/"))
        except KeyError:
            return None


def read_epub(file_path: str) -> EpubBook:
    """
    读取 EPUB，返回 EpubBook。失败抛异常（由调用方捕获处理）。
    """
    book = EpubBook()
    with zipfile.ZipFile(file_path, "r") as zf:
        opf_path = _parse_container(zf)
        if not opf_path:
            raise ValueError("EPUB 缺少 OPF 包文档（container.xml 无 rootfile）")
        book._opf_dir = posixpath.dirname(opf_path)
        opf_data = zf.read(opf_path)
        opf_root = ET.fromstring(opf_data)

        # ── 解析 metadata（Dublin Core）──
        dc_map = {}  # name -> (text, attrs)
        dc_keys = {
            "title": "title",
            "creator": "creator",
            "publisher": "publisher",
            "identifier": "identifier",
            "language": "language",
            "date": "date",
            "description": "description",
        }
        for el in opf_root.iter():
            if _local_name(el.tag) == "metadata":
                for child in el:
                    cln = _local_name(child.tag)
                    if cln in dc_keys and dc_keys[cln] not in dc_map:
                        text = (child.text or "").strip()
                        if text:
                            dc_map[dc_keys[cln]] = (text, dict(child.attrib))
        if dc_map:
            book._metadata["DC"] = {
                k: [(v, attrs)] for k, (v, attrs) in dc_map.items()
            }

        # ── 解析 manifest ──
        manifest_items = {}  # id -> (href, media_type)
        for el in opf_root.iter():
            if _local_name(el.tag) == "item":
                iid = el.attrib.get("id")
                href = el.attrib.get("href")
                mt = el.attrib.get("media-type", "")
                if iid and href:
                    manifest_items[iid] = (href, mt)

        # ── 解析 spine（决定文档阅读顺序）──
        spine_ids = []
        for el in opf_root.iter():
            if _local_name(el.tag) == "spine":
                for child in el:
                    if _local_name(child.tag) == "itemref":
                        ref = child.attrib.get("idref")
                        if ref:
                            spine_ids.append(ref)

        # 文档项：优先按 spine 顺序，否则按 manifest 顺序
        doc_ids = list(spine_ids) if spine_ids else [
            iid for iid, (_, mt) in manifest_items.items()
            if mt in ("application/xhtml+xml", "application/html+xml", "text/html")
        ]
        for iid in doc_ids:
            if iid not in manifest_items:
                continue
            href, mt = manifest_items[iid]
            content = _resolve(zf, book._opf_dir, href)
            if content is not None:
                book._items.append(
                    _EpubItem(href, mt or "application/xhtml+xml", content)
                )

        # 图片项：所有 image/* media-type
        for iid, (href, mt) in manifest_items.items():
            if mt.startswith("image/"):
                content = _resolve(zf, book._opf_dir, href)
                if content is not None:
                    book._items.append(_EpubItem(href, mt, content))

    return book
