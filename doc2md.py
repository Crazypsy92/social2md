#!/usr/bin/env python3
"""
Document to Markdown Converter — 文档批量转 Markdown
遍历目录下所有 PDF/DOCX/PPT/PPTX/XLS/XLSX 等文件，转为 .md 同名保存
"""

import argparse
import sys
from pathlib import Path

DOC_EXTS = {
    '.pdf', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
    '.html', '.epub', '.csv', '.json', '.xml',
}

# ── helpers ──────────────────────────────────────────────

def find_docs(root: Path) -> list[Path]:
    docs = []
    for f in root.rglob('*'):
        if f.is_file() and f.suffix.lower() in DOC_EXTS:
            docs.append(f)
    return sorted(docs)


def convert_one(src: Path, dst: Path, dry_run: bool, force: bool) -> bool:
    """Convert one file with markitdown. Returns True on success."""
    if dst.exists() and not force:
        print(f'  ⏭ 跳过 — {dst.name} 已存在')
        return True

    if dry_run:
        print(f'  🔍 [预览] {src.name} → {dst.name}')
        return True

    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(src))
        text = result.text_content

        if not text or not text.strip():
            print(f'  ⚠ 空内容 — {src.name}')
            # still save empty file so user knows it was processed
            dst.write_text('', encoding='utf-8')
            return True

        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding='utf-8')
        size_kb = len(text) / 1024
        print(f'  ✅ 已保存: {dst.name} ({size_kb:.1f} KB)')
        return True

    except Exception as e:
        print(f'  ❌ 失败: {e}')
        return False


# ── main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='文档批量转 Markdown — 遍历目录，转换后保留目录结构',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python doc2md.py -s D:\\教程 -d D:\\output
  python doc2md.py -s D:\\教程1 -s D:\\教程2 -d D:\\output --dry-run
  python doc2md.py -s D:\\教程 -d D:\\output --force
        '''
    )
    parser.add_argument('-s', '--src', action='append', required=True,
                        help='源目录（可多次指定）')
    parser.add_argument('-d', '--dst', required=True,
                        help='目标根目录')
    parser.add_argument('--dry-run', action='store_true',
                        help='预览模式，不实际转换')
    parser.add_argument('--force', action='store_true',
                        help='强制覆盖已有 .md 文件')
    args = parser.parse_args()

    # Validate
    src_dirs = [Path(s) for s in args.src]
    for s in src_dirs:
        if not s.is_dir():
            print(f'❌ 源目录不存在: {s}')
            sys.exit(1)

    dst_root = Path(args.dst)

    # For each source dir, collect docs
    all_tasks = []  # (src_file, dst_file)
    for src_dir in src_dirs:
        docs = find_docs(src_dir)
        src_name = src_dir.name  # top-level folder name
        for doc in docs:
            rel = doc.relative_to(src_dir)
            dst_file = dst_root / src_name / rel.with_suffix('.md')
            all_tasks.append((doc, dst_file))

    if not all_tasks:
        print('📭 未找到可转换的文件')
        return

    total = len(all_tasks)
    print(f'📁 源目录: {len(src_dirs)} 个')
    print(f'📄 共 {total} 个文件待转换')
    print(f'📂 目标: {dst_root}')
    if args.dry_run:
        print('🔍 === 预览模式：不会实际转换 ===')
    print('=' * 50)

    ok = fail = 0
    for i, (src, dst) in enumerate(all_tasks, 1):
        rel_path = dst.relative_to(dst_root)
        print(f'[{i}/{total}] {rel_path}')
        if convert_one(src, dst, args.dry_run, args.force):
            ok += 1
        else:
            fail += 1

    print('\n' + '=' * 50)
    print(f'✅ 完成！成功 {ok} 个，失败 {fail} 个')
    if args.dry_run:
        print('🔍 预览模式未实际转换，去掉 --dry-run 正式运行')


if __name__ == '__main__':
    main()