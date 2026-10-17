#!/usr/bin/env python3
"""校验「AI 只给文稿插标点/断句、没有动原文」是否真的做到了。

用法：
    python check_punct.py 原文.txt 补标点后.txt
    python check_punct.py 原文.txt 补标点后.txt --json

原理：
    保留原文全部非空白字符，只允许插入白名单内的语句标点。
    数字、正负号、小数点、单位符号和英文词边界另作保护。
    通过只说明字符约束满足；断句是否符合原意仍需人工核对。

为什么需要它：
    LLM 做标点/断句时即使 prompt 写了「不增删改」，仍会有小概率漂移。
    VideoCaptioner 的做法就是拿 difflib 相似度卡 0.96 再重做。
    不允许删除或替换原有标点，也不允许添加数学符号改变数字含义。

退出码：0 一致 / 1 不一致 / 2 用法错误
"""

import argparse
import difflib
import json
import re
import sys

# 分段标记先整体剔除，否则 <br> 里的字母会被当成正文
_LEFTOVER_SEGMENT = re.compile(r'<\s*/?\s*(br|p|hr)\s*/?\s*>|\\n|\|\|', re.IGNORECASE)


def normalize(text):
    """Keep existing punctuation, symbols and combining characters."""
    return ''.join(ch for ch in text if not ch.isspace())


INSERTABLE = frozenset('，。！？；：、…“”‘’（）《》【】「」『』,.!?;:\'"()[]')
PROTECTED = re.compile(r'[+\-−]?\d+(?:[.,:/]\d+)*(?:[%％‰])?|[A-Za-z]+(?:[\'’][A-Za-z]+)*')


def validate(original, revised):
    a, b = normalize(original), normalize(revised)
    if PROTECTED.findall(original) != PROTECTED.findall(revised):
        return False, 'numeric_or_word_token_changed'
    index = 0
    for ch in b:
        if index < len(a) and ch == a[index]:
            index += 1
        elif ch not in INSERTABLE:
            return False, 'source_changed_or_disallowed_insertion'
    return (True, None) if index == len(a) else (False, 'source_character_deleted')


def punct_stats(text):
    """统计各类标点数量，用来判断「到底加了没有」。"""
    kinds = {
        '逗号': '，,',
        '句号': '。.',
        '问号': '？?',
        '叹号': '！!',
        '顿号': '、',
        '分号': '；;',
        '冒号': '：:',
    }
    stats = {k: sum(text.count(c) for c in v) for k, v in kinds.items()}
    stats['分段标记'] = len(_LEFTOVER_SEGMENT.findall(text)) + text.count('\n')
    return stats


def first_diff(a, b, width=24):
    """返回第一处差异的描述与两侧上下文。"""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        lo_a = max(0, i1 - width)
        lo_b = max(0, j1 - width)
        return {
            'kind': tag,
            'orig_index': i1,
            'new_index': j1,
            'orig_fragment': a[i1:i2][:60] or '（无）',
            'new_fragment': b[j1:j2][:60] or '（无）',
            'orig_context': a[lo_a:i2 + width],
            'new_context': b[lo_b:j2 + width],
        }
    return None


def main():
    ap = argparse.ArgumentParser(
        description='只允许插入语句标点和空白；保留原有字符、数字与符号')
    ap.add_argument('original', help='原始文稿（无标点或带标点均可）')
    ap.add_argument('revised', help='补标点/断句后的文稿')
    ap.add_argument('--json', action='store_true', help='输出 JSON 便于程序解析')
    ap.add_argument('--quiet', action='store_true', help='只输出结论一行')
    args = ap.parse_args()

    try:
        with open(args.original, encoding='utf-8') as f:
            orig = f.read()
        with open(args.revised, encoding='utf-8') as f:
            rev = f.read()
    except OSError as exc:
        print(f'读取失败: {exc}', file=sys.stderr)
        return 2

    a, b = normalize(orig), normalize(rev)
    ok, reason = validate(orig, rev)
    diff = None if ok else first_diff(a, b)
    report = {
        'ok': ok,
        'orig_chars': len(a),
        'revised_chars': len(b),
        'punct': punct_stats(rev),
        'diff': diff,
        'reason': reason,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    if ok:
        if not args.quiet:
            st = report['punct']
            added = sum(v for k, v in st.items() if k != '分段标记')
            print(f'✓ 通过：原文 {len(a)} 个非空白字符保留，数字与英文词未变')
            print('  此检查不证明断句语义正确，引用前仍需人工核对')
            print(f'  补标点版共插入 {added} 个标点 / {st["分段标记"]} 处分段')
            if added == 0 and st['分段标记'] <= 1:
                print('  提示：没有检测到新增标点或分段，可能压根没处理')
        return 0

    print('✗ 不通过：原有字符或受保护内容改变，或插入了不允许的符号')
    print(f'  原文 {len(a)} 字 → 补标点版 {len(b)} 字（差 {len(b) - len(a):+d}）')
    if diff:
        print(f'  第一处差异：{diff["kind"]}（原文第 {diff["orig_index"]} 字附近）')
        print(f'    原文  …{diff["orig_context"]}…')
        print(f'    改动后 …{diff["new_context"]}…')
        if diff['kind'] == 'replace':
            print(f'    具体：`{diff["orig_fragment"]}` → `{diff["new_fragment"]}`')
        elif diff['kind'] == 'delete':
            print(f'    具体：原文 `{diff["orig_fragment"]}` 被删掉了')
        elif diff['kind'] == 'insert':
            print(f'    具体：多出了 `{diff["new_fragment"]}`')
    print('  处理：让模型只插标点重做，或保留无标点原文')
    return 1


if __name__ == '__main__':
    sys.exit(main())
