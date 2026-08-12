#!/usr/bin/env python3
"""合并 terms/ 目录下全部 .json 词典与 cache.json 生成 terms.js（window.TERMS = {...}）。

terms/ 内按文件名排序合并（后者覆盖前者），cache.json 最后合并、优先级最高；
任一文件缺失或损坏时跳过（视为空）。key 一律转小写，与词典格式约定一致。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_json(path):
    """读 JSON 词典；缺失/损坏/非对象时返回 {}，key 统一转小写。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).lower(): v for k, v in data.items() if isinstance(k, str)}


def main():
    terms = {}
    tdir = os.path.join(HERE, "terms")
    if os.path.isdir(tdir):
        for name in sorted(os.listdir(tdir)):  # 按文件名排序，后者覆盖前者
            if name.endswith(".json"):
                terms.update(load_json(os.path.join(tdir, name)))
    terms.update(load_json(os.path.join(HERE, "cache.json")))  # cache 覆盖 terms/
    out = os.path.join(HERE, "terms.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.TERMS = ")
        json.dump(terms, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write(";\n")
    print("terms.js: %d 条" % len(terms))


if __name__ == "__main__":
    main()
