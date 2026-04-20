"""
Step 0: PDF Parsing
===================
从 FAA Airplane Flying Handbook PDF 中提取 Emergency Procedures 章节，
按程序分割为独立 txt 文件，供 01_extract.py 批量处理。

使用方法:
    python scripts/00_pdf_parse.py --pdf data/airplane_flying_handbook.pdf
    python scripts/00_pdf_parse.py --pdf data/AFH.pdf --output-dir data/procedures

下载 PDF:
    https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/airplane_handbook
    下载 FAA-H-8083-3C (Airplane Flying Handbook)，放到 data/ 目录。
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Windows GBK 终端兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() in ('gbk', 'cp936', 'gb2312'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import pdfplumber
except ImportError:
    sys.exit("❌ 缺少依赖: pip install pdfplumber")


# ── 章节检测模式 ────────────────────────────────────────────────
# FAA-H-8083-3C 中 Emergency Procedures 为 Chapter 18
CHAPTER_START_PATTERNS = [
    re.compile(r'chapter\s+18\b', re.IGNORECASE),
    re.compile(r'emergency\s+procedures', re.IGNORECASE),
]
CHAPTER_END_PATTERNS = [
    re.compile(r'chapter\s+19\b', re.IGNORECASE),
    re.compile(r'\bglossary\b', re.IGNORECASE),
    re.compile(r'\bappendix\b', re.IGNORECASE),
    re.compile(r'\bindex\b', re.IGNORECASE),
]

# 程序标题：混合大小写短行，首字母大写，不含句号结尾
# 匹配如 "Engine Failure After Takeoff (Single-Engine)"、"In-Flight Fire" 等
PROCEDURE_HEADING_RE = re.compile(
    r'^[A-Z][A-Za-z0-9 \-/()\u2019]+$'
)

# 页眉/页脚清除模式
HEADER_FOOTER_PATTERNS = [
    re.compile(r'^airplane\s+flying\s+handbook\s*$', re.IGNORECASE),
    re.compile(r'^chapter\s+18\s*$', re.IGNORECASE),
    re.compile(r'^emergency\s+procedures\s*$', re.IGNORECASE),
    re.compile(r'^\d+$'),          # 独立页码行
    re.compile(r'^18-\d+$'),       # 章节页码如 "18-1"
    re.compile(r'^faa-h-\d+', re.IGNORECASE),  # 文件编号行
]


def find_chapter_pages(pdf) -> tuple[int, int]:
    """
    扫描 PDF 找到 Chapter 17 的起止页码（0-indexed）。
    返回 (start_page, end_page)，end_page 不含。
    """
    start_page = None
    end_page = len(pdf.pages)

    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        text_lower = text.lower()

        if start_page is None:
            if any(p.search(text_lower) for p in CHAPTER_START_PATTERNS):
                # 验证：必须在同一页既有 "chapter 18" 又有 emergency 相关内容
                has_ch18 = bool(re.search(r'chapter\s+18', text_lower))
                has_emerg = bool(re.search(r'emergency', text_lower))
                if has_ch18 or (has_emerg and i > 10):  # 跳过前 10 页避免目录页
                    start_page = i
                    print(f"   找到章节起始页: 第 {i+1} 页")
        else:
            # 检查是否到达下一章
            if any(p.search(text_lower) for p in CHAPTER_END_PATTERNS):
                end_page = i
                print(f"   找到章节结束页: 第 {i+1} 页（不含）")
                break

    if start_page is None:
        # 单章 PDF 可能第 1 页就是正文，没有 "Chapter 18" 标题页
        print("   ⚠️  未找到章节标题，假定整个 PDF 均为目标章节内容")
        start_page = 0

    return start_page, end_page


def clean_text(raw_text: str) -> str:
    """清理提取的文本：去页眉/页脚，修复连字符换行，规范空行。"""
    lines = raw_text.splitlines()
    cleaned = []

    for line in lines:
        stripped = line.strip()

        # 跳过页眉/页脚行
        if any(p.match(stripped) for p in HEADER_FOOTER_PATTERNS):
            continue

        # 跳过空的短行（页面顶部/底部的孤立空格）
        cleaned.append(stripped)

    text = "\n".join(cleaned)

    # 修复跨行连字符：word-\nnext → wordnext
    text = re.sub(r'(\w+)-\n(\w)', r'\1\2', text)

    # 3+ 个空行合并为 2 个
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def extract_chapter_text(pdf, start_page: int, end_page: int) -> str:
    """提取指定页范围的文本并清理。"""
    pages = pdf.pages[start_page:end_page]
    raw_parts = []

    for page in pages:
        text = page.extract_text()
        if text:
            raw_parts.append(text)

    raw_text = "\n\n".join(raw_parts)
    return clean_text(raw_text)


SKIP_HEADING_PREFIXES = ('Figure', 'NOTE', 'Note', 'Table', '⦁', '[Figure')

def is_procedure_heading(line: str, prev_line: str = '', next_line: str = '') -> bool:
    """
    判断一行是否为章节标题。
    FAA PDF 的标题规律：短行、首字母大写、前一行以句号结尾（或为空行）、后一行是段落正文
    """
    stripped = line.strip()
    if len(stripped) < 4 or len(stripped) > 80:
        return False
    if stripped.endswith(('.', ',', ';', ':')):
        return False
    if any(stripped.startswith(p) for p in SKIP_HEADING_PREFIXES):
        return False
    if not stripped[0].isupper():
        return False
    if not PROCEDURE_HEADING_RE.match(stripped):
        return False

    prev_stripped = prev_line.strip()
    next_stripped = next_line.strip()

    # 前一行：空行，或以句号/右括号/感叹号结尾（句子结束）
    prev_ok = (not prev_stripped) or prev_stripped.endswith(('.', ')', '!', '?'))
    # 后一行：空行，或非空的段落行（不是另一个短标题候选）
    next_ok = (not next_stripped) or len(next_stripped) > 40

    return prev_ok and next_ok


def split_into_procedures(text: str) -> list[tuple[str, str]]:
    """
    按程序标题分割章节文本。
    返回 [(procedure_title, procedure_text), ...]
    """
    lines = text.splitlines()
    procedures = []
    current_title = None
    current_lines = []

    # 在第一个标题之前可能有章节介绍段落
    preamble_lines = []
    found_first_heading = False

    for i, line in enumerate(lines):
        prev_line = lines[i-1] if i > 0 else ''
        next_line = lines[i+1] if i < len(lines) - 1 else ''
        if is_procedure_heading(line, prev_line, next_line):
            if True:
                if not found_first_heading:
                    found_first_heading = True
                    preamble_lines = current_lines[:]
                    current_lines = []

                if current_title is not None:
                    body = "\n".join(current_lines).strip()
                    if body:
                        procedures.append((current_title, body))

                current_title = line.strip()
                current_lines = []
                continue

        current_lines.append(line)

    # 最后一个程序
    if current_title is not None:
        body = "\n".join(current_lines).strip()
        if body:
            procedures.append((current_title, body))

    # 如果没有检测到任何程序，将整章作为一个文件
    if not procedures:
        print("   ⚠️  未能自动分割程序，将整章保存为单个文件。")
        procedures = [("EMERGENCY PROCEDURES", text)]

    return procedures


def slugify(title: str) -> str:
    """将程序标题转为合法文件名。"""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    slug = slug.strip('_')
    return slug


def save_procedures(procedures: list[tuple[str, str]], output_dir: Path):
    """将每个程序保存为独立 txt 文件，并生成索引。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_txt_files = list(output_dir.glob("*.txt"))
    if existing_txt_files:
        archive_dir = output_dir / "_archive" / datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir.mkdir(parents=True, exist_ok=True)

        print(f"   🗃️  归档现有 txt 文件到: {archive_dir}")
        for old_file in existing_txt_files:
            old_file.rename(archive_dir / old_file.name)

    index_lines = ["Emergency Procedures — 文件索引", "=" * 40, ""]
    saved_count = 0

    for idx, (title, content) in enumerate(procedures, start=1):
        filename = f"{idx:02d}_{slugify(title)}.txt"
        filepath = output_dir / filename

        full_text = f"{title}\n{'=' * len(title)}\n\n{content}"
        filepath.write_text(full_text, encoding="utf-8")

        index_lines.append(f"{idx:02d}. {title}")
        index_lines.append(f"    → {filename}")
        index_lines.append("")
        saved_count += 1
        print(f"   💾 [{idx:02d}] {title}")

    # 写入索引
    index_path = output_dir / "index.txt"
    index_path.write_text("\n".join(index_lines), encoding="utf-8")

    return saved_count


def main():
    parser = argparse.ArgumentParser(
        description="从 FAA AFH PDF 提取 Emergency Procedures 章节，按程序分割为独立 txt 文件"
    )
    parser.add_argument(
        "--pdf",
        default="data/afh_chapter18_emergency_procedures.pdf",
        help="PDF 文件路径（默认: data/afh_chapter18_emergency_procedures.pdf）"
    )
    parser.add_argument(
        "--output-dir",
        default="data/procedures",
        help="输出目录（默认: data/procedures）"
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=None,
        help="手动指定章节起始页码（1-indexed），跳过自动检测"
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="手动指定章节结束页码（1-indexed，不含）"
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    output_dir = Path(args.output_dir)

    # 检查 PDF 是否存在
    if not pdf_path.exists():
        print(f"""
❌ 未找到 PDF 文件: {pdf_path}

📥 请下载 Chapter 18: Emergency Procedures (单章 PDF，几 MB):
   https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/airplane_handbook

   在页面中找到 "Chapter 18: Emergency Procedures (PDF)" 并下载，
   保存为: {pdf_path.resolve()}

   或使用 --pdf 参数指定自定义路径：
   python scripts/00_pdf_parse.py --pdf /你的路径/chapter18.pdf
""")
        sys.exit(1)

    print(f"📄 打开 PDF: {pdf_path}")

    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        print(f"   共 {total_pages} 页")

        # 确定页码范围
        if args.start_page is not None:
            start = args.start_page - 1  # 转为 0-indexed
            end = (args.end_page - 1) if args.end_page else total_pages
            print(f"   手动指定范围: 第 {start+1}–{end} 页")
        else:
            print("🔍 自动检测 Emergency Procedures 章节...")
            start, end = find_chapter_pages(pdf)

        page_count = end - start
        print(f"   章节共 {page_count} 页")

        # 提取并清理文本
        print("📝 提取章节文本...")
        chapter_text = extract_chapter_text(pdf, start, end)
        print(f"   提取文本长度: {len(chapter_text)} 字符")

        # 按程序分割
        print("✂️  按程序标题分割...")
        procedures = split_into_procedures(chapter_text)
        print(f"   检测到 {len(procedures)} 个程序段落")

        # 保存文件
        print(f"\n💾 保存到 {output_dir}/")
        count = save_procedures(procedures, output_dir)

    print(f"""
✅ 完成！共保存 {count} 个程序文件。

📁 输出目录: {output_dir.resolve()}
📋 索引文件: {output_dir}/index.txt

下一步：
    python scripts/01_extract.py --input-dir {output_dir}
""")


if __name__ == "__main__":
    main()
