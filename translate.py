#!/usr/bin/env python3
"""话语权翻译机 CLI：英文段切分、查词典、批量调 LLM、写缓存、回填。

用法：
  python3 translate.py "要翻译的文本"
  python3 translate.py --file input.txt
  cat input.txt | python3 translate.py
选项：
  --mode a|b   翻译模式，默认 a（a=中英混合只换英文，b=纯英文逐词硬翻）
  --no-llm     离线模式：只用词典+缓存，未命中词保持原样
"""

import argparse
import json
import os
import re
import sys

import llm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TERMS_DIR = os.path.join(BASE_DIR, "terms")
CACHE_PATH = os.path.join(BASE_DIR, "cache.json")

# 英文段：允许段内以单个空格或 . # _ - 连接（Windows 11 / C++ / base_url / GPT-5.6）
SEG_RE = re.compile(r"[A-Za-z0-9]+(?:[ \t.+#_-][A-Za-z0-9]+)*")
# 模式 B 的单词核心：剥离首尾标点
TOKEN_RE = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.S)


def load_json_dict(path):
    """读扁平 JSON 词典，key 统一小写；文件缺失或损坏返回 {}。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"警告: 读取 {path} 失败: {e}", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            out[k.strip().lower()] = v.strip()
    return out


def load_terms_dir():
    """加载 terms/ 目录下全部 .json 词典合并（按文件名排序，后者覆盖前者）。"""
    merged = {}
    if not os.path.isdir(TERMS_DIR):
        return merged
    for name in sorted(os.listdir(TERMS_DIR)):
        if name.endswith(".json"):
            merged.update(load_json_dict(os.path.join(TERMS_DIR, name)))
    return merged


def save_cache(cache):
    """写 cache.json（格式同 seed.json）。"""
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"警告: 写入缓存失败: {e}", file=sys.stderr)


def _boundary_ok(lower, i, k, n):
    """词边界检查：key 首尾若为字母/数字，相邻字符不得再是字母/数字。

    防止常见短词切碎专有名词（如 ai 不再切碎 chain、son 不再切碎 Sonnet）。
    """
    if k[0].isalnum() and i > 0 and lower[i - 1].isalnum():
        return False
    end = i + len(k)
    if k[-1].isalnum() and end < n and lower[end].isalnum():
        return False
    return True


def split_segment(seg, lookup, keys_desc):
    """整段查词典；未命中则从左到右最长匹配切分，连续残余收为未知词。

    返回 [(文本, 译名或 None)]，None 表示未知词。
    """
    if seg.lower() in lookup:
        return [(seg, lookup[seg.lower()])]
    pieces = []
    lower = seg.lower()
    i, n = 0, len(seg)
    buf = []

    def flush():
        if buf:
            pieces.append(("".join(buf), None))
            del buf[:]

    while i < n:
        best = None
        for k in keys_desc:  # 按键长降序，命中即最长匹配
            if lower.startswith(k, i) and _boundary_ok(lower, i, k, n):
                best = k
                break
        if best is not None:
            flush()
            pieces.append((seg[i:i + len(best)], lookup[best]))
            i += len(best)
        else:
            buf.append(seg[i])
            i += 1
    flush()
    return pieces


def apply_llm(unknowns, cache, no_llm):
    """未知词去重后一次批量调 LLM，并入并保存缓存。

    返回 {原文: 译名}（key 已小写），未命中/离线返回 {}。
    """
    if no_llm or not unknowns:
        return {}
    terms, seen = [], set()
    for _, _, t in unknowns:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            terms.append(t)
    if not terms:
        return {}
    try:
        result = llm.translate_terms(terms)
    except Exception:
        result = {}
    new_entries = {}
    for k, v in result.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            new_entries[k.strip().lower()] = v.strip()
    if new_entries:
        cache.update(new_entries)
        save_cache(cache)
    return new_entries


def backfill(output, unknowns, result):
    """把译名原位回填（直接替换不加空格）；result 的 key 已小写。"""
    if not result:
        return output
    swaps = []
    for start, end, term in unknowns:
        v = result.get(term.strip().lower())
        if v:
            swaps.append((start, end, v))
    for start, end, v in sorted(swaps, reverse=True):  # 从右往左替换，偏移不变
        output = output[:start] + v + output[end:]
    return output


def translate_mode_a(text, lookup, keys_desc, cache, no_llm):
    """模式 A：中英混合输入，只换英文术语。"""
    parts = []
    unknowns = []  # (起点, 终点, 未知词)，坐标为输出串中的绝对位置
    pos = 0
    last = 0
    for m in SEG_RE.finditer(text):
        parts.append(text[last:m.start()])
        pos += m.start() - last
        for ptext, repl in split_segment(m.group(), lookup, keys_desc):
            if repl is None:
                term = ptext.strip()
                parts.append(ptext)
                if term:
                    unknowns.append((pos, pos + len(ptext), term))
                pos += len(ptext)
            else:
                parts.append(repl)
                pos += len(repl)
        last = m.end()
    parts.append(text[last:])
    output = "".join(parts)
    result = apply_llm(unknowns, cache, no_llm)
    return backfill(output, unknowns, result)


def translate_mode_b(text, lookup, cache, no_llm):
    """模式 B：纯英文输入，按空格逐词硬翻（标点保留）。"""
    parts = []
    unknowns = []
    pos = 0
    for token in re.split(r"(\s+)", text):
        if not token or token.isspace():
            parts.append(token)
            pos += len(token)
            continue
        m = TOKEN_RE.match(token)
        lead, core, trail = m.group(1), m.group(2), m.group(3)
        if not core:
            parts.append(token)
            pos += len(token)
            continue
        repl = lookup.get(core.lower())
        if repl:
            parts.append(lead + repl + trail)
            pos += len(lead) + len(repl) + len(trail)
        else:
            parts.append(token)
            start = pos + len(lead)
            unknowns.append((start, start + len(core), core))
            pos += len(token)
    output = "".join(parts)
    result = apply_llm(unknowns, cache, no_llm)
    return backfill(output, unknowns, result)


def parse_args(argv):
    p = argparse.ArgumentParser(description="话语权翻译机：把英文术语翻成官方定名/直译腔中文")
    p.add_argument("text", nargs="?", default=None, help="要翻译的文本")
    p.add_argument("--file", metavar="PATH", default=None, help="从文件读取输入")
    p.add_argument("--mode", choices=["a", "b"], default="a", help="翻译模式，默认 a")
    p.add_argument("--no-llm", action="store_true",
                   help="离线模式：只用词典+缓存，未命中词保持原样")
    return p.parse_args(argv)


def read_input(args):
    if args.file:
        try:
            with open(args.file, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            print(f"错误: 无法读取文件 {args.file}: {e}", file=sys.stderr)
            sys.exit(1)
    if args.text is not None:
        return args.text
    if sys.stdin.isatty():
        print('用法: python3 translate.py "文本" / --file 文件 / stdin 管道输入',
              file=sys.stderr)
        sys.exit(1)
    return sys.stdin.read()


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    text = read_input(args)
    seed = load_terms_dir()
    cache = load_json_dict(CACHE_PATH)
    lookup = dict(seed)
    lookup.update(cache)  # 缓存优先于种子词典
    keys_desc = sorted(lookup, key=len, reverse=True)
    if args.mode == "a":
        output = translate_mode_a(text, lookup, keys_desc, cache, args.no_llm)
    else:
        output = translate_mode_b(text, lookup, cache, args.no_llm)
    if not output.endswith("\n"):
        output += "\n"
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
