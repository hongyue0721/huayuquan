#!/usr/bin/env python3
"""合并 terms/ 目录下全部 .json 词典与 cache.json 生成 词库.js（window.词库 = {...}）。

terms/ 内按文件名排序合并（后者覆盖前者），惟 contrib.json（词库呈批贡献词库）殿后、
压过内置词库；cache.json 最后合并、优先级最高；
任一文件缺失或损坏时跳过（视为空）。key 一律转小写，与词典格式约定一致。
"""
import json
import os

本目录 = os.path.dirname(os.path.abspath(__file__))


def 读词典(路径):
    """读 JSON 词典；缺失/损坏/非对象时返回 {}，key 统一转小写。"""
    try:
        with open(路径, "r", encoding="utf-8") as f:
            数据 = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(数据, dict):
        return {}
    return {str(k).lower(): v for k, v in 数据.items() if isinstance(k, str)}


def 主程序():
    词条 = {}
    词典目录 = os.path.join(本目录, "terms")
    if os.path.isdir(词典目录):
        for 文件名 in sorted(os.listdir(词典目录), key=lambda f: (f == "contrib.json", f)):  # 按文件名排序，contrib.json 殿后优先
            if 文件名.endswith(".json"):
                词条.update(读词典(os.path.join(词典目录, 文件名)))
    词条.update(读词典(os.path.join(本目录, "cache.json")))  # 缓存覆盖 terms/
    输出路径 = os.path.join(本目录, "词库.js")
    with open(输出路径, "w", encoding="utf-8") as f:
        f.write("window.词库 = ")
        json.dump(词条, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write(";\n")
    print("词库.js: %d 条" % len(词条))


if __name__ == "__main__":
    主程序()
