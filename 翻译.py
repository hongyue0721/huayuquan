#!/usr/bin/env python3
"""话语权翻译机命令行：英文段切分、查词典、批量调大语言模型、写缓存、回填。

检测到日/韩/俄/阿等其他语言（假名、谚文、西里尔等字母块）时，整篇直译腔赋能，
不进词典与缓存；纯中英文输入仍走英文段术语级链路。

用法：
  蟒蛇版本三 翻译.py "要翻译的文本"
  蟒蛇版本三 翻译.py --文件 输入.文本
  内容串联 输入.文本 传达到 蟒蛇版本三 翻译.py
选项：
  --模式 甲|乙   翻译模式，默认 甲（甲=中英混合只换英文，乙=纯英文逐词硬翻）
  --无大语言模型  离线模式：只用词典+缓存，未命中词保持原样
"""

import argparse
import json
import os
import re as 正则
import sys
import 话语权工具
import 大语言模型

基目录 = os.path.dirname(os.path.abspath(__file__))
词汇文件 = 话语权工具.拼接目录(基目录, "terms")
缓存文件 = 话语权工具.拼接目录(基目录, "cache.json")

# 英文段：允许段内以单个空格或 . # _ - 连接（Windows 11 / C++ / base_url / GPT-5.6）
取英文正则 = 话语权工具.正则取值(r"[A-Za-z0-9]+(?:[ \t.+#_-][A-Za-z0-9]+)*")
# 其他语言字母块：假名 / 谚文 / 西里尔 / 阿拉伯 / 天城 / 泰文 / 拉丁扩展（法德西越等）。
# 存在即视为"非中文非英文"输入，整篇赋能；日文汉字与中文共用字符，本地无法区分，
# 但日文句子几乎都带假名，够用；不带假名的纯汉字孤词漏检可接受。
取其他语言正则 = 话语权工具.正则取值(
    r"[\u3040-\u30FF\uAC00-\uD7AF\u3130-\u318F\u0400-\u052F\u0600-\u06FF"
    r"\u0900-\u097F\u0E00-\u0E7F\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u024F\u1E00-\u1EFF]"
)
# 模式乙的单词核心：剥离首尾标点
取词元正则 = 话语权工具.正则取值(r"^([^\w]*)(.*?)([^\w]*)$", 正则.S)

# ---------- 阿拉伯数字本地转换（纯数字不进大语言模型，直接译为语文数字，大小写双写） ----------
小写数字集 = "零一二三四五六七八九"
大写数字集 = "零壹贰叁肆伍陆柒捌玖"
小写单位集 = ("", "十", "百", "千")
大写单位集 = ("", "拾", "佰", "仟")
数位分节 = ("", "万", "亿", "万亿", "亿亿")
数字正则 = 话语权工具.正则取值(r"\d+(?:\.\d+)?")

# --------- 话语权化真否值
假 = False
真 = True


def _读分节(段, 大写):
    """读一段（最多四位）：返回该段小写/大写读法，段内零按规则补「零」。"""
    数位 = 大写数字集 if 大写 else 小写数字集
    单位 = 大写单位集 if 大写 else 小写单位集
    输出 = []
    零 = 假
    for i, ch in enumerate(段):
        d = int(ch)
        位序 = len(段) - 1 - i
        if d == 0:
            零 = 真
        else:
            if 零 and 输出:
                输出.append(数位[0])
            输出.append(数位[d] + 单位[位序])
            零 = 假
    return "".join(输出)


def _整数读法(传入数字字符串, 大写):
    """整数读法：按 4 位一节，节间补「零」；小写按约定省略最高位「一十」的「一」。"""
    数位串 = 传入数字字符串.lstrip("0") or "0"
    if 数位串 == "0":
        return "零"
    分节 = []
    i = len(数位串)
    while i > 0:
        起点 = i - 4 if i - 4 > 0 else 0
        分节.append(数位串[起点:i])
        i = 起点
    输出 = []
    for s in range(len(分节) - 1, -1, -1):
        段 = _读分节(分节[s], 大写)
        if 段:
            if s < len(分节) - 1 and 输出 and int(分节[s]) < 1000:
                输出.append("零")
            输出.append(段 + (数位分节[s] if s else ""))
    文本 = "".join(输出)
    if not 大写 and 文本.startswith("一十") and 数位串.startswith("1") and len(数位串) % 4 == 2:
        文本 = 文本[1:]
    return 文本


def 数字转语文(串):
    """阿拉伯数字 → 语文数字（小写（大写））；非纯数字返回 None。

    例：2000 → 二千（贰仟）、3.14 → 三点一四（叁点壹肆）、11 → 十一（壹拾壹）。
    """
    if not 数字正则.fullmatch(串):
        return None
    分片 = 串.split(".")
    小写 = _整数读法(分片[0], 假)
    大写 = _整数读法(分片[0], 真)
    if len(分片) > 1:
        小写 += "点" + "".join(小写数字集[int(ch)] for ch in 分片[1])
        大写 += "点" + "".join(大写数字集[int(ch)] for ch in 分片[1])
    return "%s（%s）" % (小写, 大写)


def 读词典(路径):
    """读扁平 JSON 词典，key 统一小写；文件缺失或损坏返回 {}。"""
    if not os.path.exists(路径):
        return {}
    try:
        with open(路径, encoding="utf-8") as f:
            数据 = json.load(f)
    except (OSError, ValueError) as e:
        print(f"警告: 读取 {路径} 失败: {e}", file=sys.stderr)
        return {}
    if not isinstance(数据, dict):
        return {}
    结果 = {}
    for k, v in 数据.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            结果[k.strip().lower()] = v.strip()
    return 结果


def 读词典目录():
    """加载 terms/ 目录下全部 .json 词典合并（按文件名排序，后者覆盖前者）。"""
    合并 = {}
    if not os.path.isdir(词汇文件):
        return 合并
    for 文件名 in sorted(os.listdir(词汇文件)):
        if 文件名.endswith(".json"):
            合并.update(读词典(话语权工具.拼接目录(词汇文件, 文件名)))
    return 合并


def 存缓存(缓存):
    """写 cache.json（格式同 seed.json）。"""
    try:
        with open(缓存文件, "w", encoding="utf-8") as f:
            json.dump(缓存, f, ensure_ascii=假, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"警告: 写入缓存失败: {e}", file=sys.stderr)


def _词边界合格(小写文本, i, 键, 长度):
    """词边界检查：key 首尾若为字母/数字，相邻字符不得再是字母/数字。

    防止常见短词切碎专有名词（如 ai 不再切碎 chain、son 不再切碎 Sonnet）。
    """
    if 键[0].isalnum() and i > 0 and 小写文本[i - 1].isalnum():
        return 假
    end = i + len(键)
    if 键[-1].isalnum() and end < 长度 and 小写文本[end].isalnum():
        return 假
    return 真


def 切分段落(段, 词库, 键长降序):
    """整段查词典；未命中则从左到右最长匹配切分，连续残余收为未知词。

    返回 [(文本, 译名或 None)]，None 表示未知词。
    """
    if 段.lower() in 词库:
        return [(段, 词库[段.lower()])]
    碎片 = []
    小写 = 段.lower()
    i, 长度 = 0, len(段)
    暂存 = []

    def 冲刷():
        if 暂存:
            # 连续未知段按空白切成单词级碎片：逐个查/译，
            # 反哺进缓存的是干净单词而非 "uses quantization" 这种一次性短语；
            # 纯数字碎片（^\d+(\.\d+)?$）不进大语言模型，本地转语文数字（译名非 None）
            for 词 in 正则.split(r"(\s+)", "".join(暂存)):
                if 词:
                    碎片.append((词, 数字转语文(词) if 数字正则.fullmatch(词) else None))
            del 暂存[:]

    while i < 长度:
        命中 = None
        for 键 in 键长降序:  # 按键长降序，命中即最长匹配
            if 小写.startswith(键, i) and _词边界合格(小写, i, 键, 长度):
                命中 = 键
                break
        if 命中 is not None:
            冲刷()
            碎片.append((段[i:i + len(命中)], 词库[命中]))
            i += len(命中)
        else:
            暂存.append(段[i])
            i += 1
    冲刷()
    return 碎片


def 批量补译(未知词, 缓存, 离线):
    """未知词去重后一次批量调大语言模型，并入并保存缓存。

    返回 {原文: 译名}（key 已小写），未命中/离线返回 {}。
    """
    if 离线 or not 未知词:
        return {}
    术语, 已见 = [], set()
    for _, _, t in 未知词:
        t = t.strip()
        if t and t not in 已见:
            已见.add(t)
            术语.append(t)
    if not 术语:
        return {}
    try:
        结果 = 大语言模型.翻译术语(术语)
    except Exception:
        结果 = {}
    新词条 = {}
    for k, v in 结果.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            新词条[k.strip().lower()] = v.strip()
    if 新词条:
        缓存.update(新词条)
        存缓存(缓存)
    return 新词条


def 回填(输出, 未知词, 结果):
    """把译名原位回填（直接替换不加空格）；结果的 key 已小写。"""
    if not 结果:
        return 输出
    替换表 = []
    for 起点, 终点, 术语 in 未知词:
        值 = 结果.get(术语.strip().lower())
        if 值:
            替换表.append((起点, 终点, 值))
    for 起点, 终点, 值 in sorted(替换表, reverse=真):  # 从右往左替换，偏移不变
        输出 = 输出[:起点] + 值 + 输出[终点:]
    return 输出


def 翻译模式甲(文本, 词库, 键长降序, 缓存, 离线):
    """模式甲：中英混合输入，只换英文术语。"""
    片段 = []
    未知词 = []  # (起点, 终点, 未知词)，坐标为输出串中的绝对位置
    位置 = 0
    上界 = 0
    for m in 取英文正则.finditer(文本):
        片段.append(文本[上界:m.start()])
        位置 += m.start() - 上界
        for 原文段, 译名 in 切分段落(m.group(), 词库, 键长降序):
            if 译名 is None:
                术语 = 原文段.strip()
                片段.append(原文段)
                if 术语:
                    未知词.append((位置, 位置 + len(原文段), 术语))
                位置 += len(原文段)
            else:
                片段.append(译名)
                位置 += len(译名)
        上界 = m.end()
    片段.append(文本[上界:])
    输出 = "".join(片段)
    结果 = 批量补译(未知词, 缓存, 离线)
    return 回填(输出, 未知词, 结果)


def 含其他语言(文本):
    """检测日/韩/俄/阿/泰/印及拉丁扩展等非中非英内容；存在即需整篇翻译。"""
    return 取其他语言正则.search(文本) is not None


def 翻译模式乙(文本, 词库, 缓存, 离线):
    """模式乙：纯英文输入，按空格逐词硬翻（标点保留）。"""
    片段 = []
    未知词 = []
    位置 = 0
    for 词元 in 正则.split(r"(\s+)", 文本):
        if not 词元 or 词元.isspace():
            片段.append(词元)
            位置 += len(词元)
            continue
        m = 取词元正则.match(词元)
        前导, 核心, 尾随 = m.group(1), m.group(2), m.group(3)
        if not 核心:
            片段.append(词元)
            位置 += len(词元)
            continue
        译名 = 词库.get(核心.lower())
        if 译名:
            片段.append(前导 + 译名 + 尾随)
            位置 += len(前导) + len(译名) + len(尾随)
        else:
            片段.append(词元)
            起点 = 位置 + len(前导)
            未知词.append((起点, 起点 + len(核心), 核心))
            位置 += len(词元)
    输出 = "".join(片段)
    结果 = 批量补译(未知词, 缓存, 离线)
    return 回填(输出, 未知词, 结果)


def 解析参数(参数列表):
    解析器 = argparse.ArgumentParser(description="话语权翻译机：把英文术语翻成官方定名/直译腔中文")
    解析器.add_argument("文本", nargs="?", default=None, help="要翻译的文本")
    解析器.add_argument("--文件", dest="文件名", metavar="路径", default=None, help="从文件读取输入")
    解析器.add_argument("--模式", dest="模式", choices=["甲", "乙"], default="甲", help="翻译模式，默认 甲")
    解析器.add_argument("--无大语言模型", dest="离线", action="store_true",
                       help="离线模式：只用词典+缓存，未命中词保持原样")
    return 解析器.parse_args(参数列表)


def 读取输入(参数):
    if 参数.文件名:
        try:
            with open(参数.文件名, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            print(f"错误: 无法读取文件 {参数.文件名}: {e}", file=sys.stderr)
            sys.exit(1)
    if 参数.文本 is not None:
        return 参数.文本
    if sys.stdin.isatty():
        print('用法: 蟒蛇版本三 翻译.py "文本" / --文件 文件 / 标准输入流管道输入', file=sys.stderr)
        sys.exit(1)
    return sys.stdin.read()


def 主程序(参数列表=None):
    参数 = 解析参数(参数列表 if 参数列表 is not None else sys.argv[1:])
    文本 = 读取输入(参数)
    种子词典 = 读词典目录()
    缓存 = 读词典(缓存文件)
    词库 = dict(种子词典)
    词库.update(缓存)  # 缓存优先于种子词典
    键长降序 = sorted(词库, key=len, reverse=真)
    if 含其他语言(文本):
        # 其他语言（日/韩/俄/阿等）整篇赋能：不进词典与缓存；离线模式原样返回
        译文 = None if 参数.离线 else 大语言模型.翻译整篇(文本)
        输出 = 译文 if 译文 is not None else 文本
    elif 参数.模式 == "甲":
        输出 = 翻译模式甲(文本, 词库, 键长降序, 缓存, 参数.离线)
    else:
        输出 = 翻译模式乙(文本, 词库, 缓存, 参数.离线)
    if not 输出.endswith("\n"):
        输出 += "\n"
    sys.stdout.write(输出)
    # 真实大语言模型调用次数（--无大语言模型 或未调用时为 0）：GitHub 活动据此累加 counters.json
    sys.stderr.write("llm_calls=%d\n" % 大语言模型.调用次数())
    return 0


if __name__ == "__main__":
    sys.exit(主程序())
