#!/usr/bin/env python3
"""词库呈批：解析呈批 issue 正文、生成呈批方案与批复公文，并将方案应用至贡献词库。

用法：
  蟒蛇版本三 词库呈批.py --校验 正文文件路径
    解析呈批正文，输出 呈批方案.json（{"添加": {原词: 译名}, "删除": [原词]}）
    与 批复.md（公文体准予批复 / 驳回通知）；
    格式有误或所呈为空（全空、全注释）时退出码非零，以示驳回。
  蟒蛇版本三 词库呈批.py --应用 方案文件路径
    把方案应用到 terms/contrib.json（不存在则创建）；
    仅动此文件，绝不触碰 terms/common.json、terms/seed.json、cache.json。
"""

import argparse
import json
import os
import re as 正则
import sys
import 话语权工具

基目录 = os.path.dirname(os.path.abspath(__file__))
贡献词库文件 = os.path.join(基目录, "terms", "contrib.json")
方案文件名 = "呈批方案.json"
批复文件名 = "批复.md"

# 添加行：`添加: 原词 = 译名`，冒号全角半角均可，等号全角半角均可，可混用
添加正则 = 话语权工具.正则取值(r"^\s*添加\s*[:：]\s*(.*?)\s*[=＝]\s*(.*?)\s*$")
# 删除行：`删除: 原词`
删除正则 = 话语权工具.正则取值(r"^\s*删除\s*[:：]\s*(.*?)\s*$")


def 解析正文(正文):
    """解析呈批正文，返回 (方案, 错误列表)。

    方案 = {"添加": {原词: 译名}, "删除": [原词]}，原词一律小写去空白；
    错误 = [(行号, 原行, 原因)]，仅收无法解析或不合规的非空行。
    空行、以 # 开头的行直接忽略；添加的译名为空视为错误。
    """
    添加 = {}
    删除 = []
    错误 = []
    for 行号, 原行 in enumerate(正文.splitlines(), start=1):
        行 = 原行.strip()
        if not 行 or 行.startswith("#"):
            continue
        添加匹配 = 添加正则.match(行)
        if 添加匹配:
            原词, 译名 = 添加匹配.group(1).strip(), 添加匹配.group(2).strip()
            if not 原词:
                错误.append((行号, 行, "缺少原词"))
            elif not 译名:
                错误.append((行号, 行, "译名为空"))
            else:
                添加[原词.lower()] = 译名
            continue
        删除匹配 = 删除正则.match(行)
        if 删除匹配:
            原词 = 删除匹配.group(1).strip()
            if not 原词:
                错误.append((行号, 行, "缺少原词"))
            elif 原词.lower() not in 删除:
                删除.append(原词.lower())
            continue
        if 行.startswith("添加"):
            错误.append((行号, 行, "缺少等号"))
        elif 行.startswith("删除"):
            错误.append((行号, 行, "缺少原词"))
        else:
            错误.append((行号, 行, "无法解析"))
    return {"添加": 添加, "删除": 删除}, 错误


def 生成批复(添加, 删除, 错误):
    """按格式合规情况生成公文体批复/驳回通知（Markdown）。

    有错误 → 驳回通知（逐条列明不合格式之处）；
    无错误但一条有效条目都没有（全空/全注释）→ 驳回通知（所呈空空如也）；
    其余 → 准予批复（所呈词条 N 条格式合规，准予收录）。
    """
    if 错误:
        明细 = "\n".join(
            "- 第 %d 行「%s」%s，不合呈批格式；" % (行号, 原行, 原因)
            for 行号, 原行, 原因 in 错误
        )
        return (
            "## 关于词库呈批的驳回通知\n\n"
            "经审核，所呈正文存在以下不合格式之处：\n\n%s\n\n"
            "驳回。请依模板重新呈递。" % 明细
        )
    if not 添加 and not 删除:
        return (
            "## 关于词库呈批的驳回通知\n\n"
            "经审核，所呈空空如也，无一条可批词条。\n\n"
            "驳回。请依模板填写后重新呈递。"
        )
    return (
        "## 关于词库呈批的批复\n\n"
        "经审核，所呈词条 %d 条格式合规，准予收录。" % (len(添加) + len(删除))
    )


def 读正文(路径):
    """读取呈文正文；文件缺失按空正文处理（所呈空空如也，走驳回）。"""
    try:
        with open(路径, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def 校验主流程(正文):
    """解析正文，输出 呈批方案.json 与 批复.md；驳回（有错误或所呈为空）时返回非零。"""
    方案, 错误 = 解析正文(正文)
    if 错误:
        方案 = {"添加": {}, "删除": []}  # 有错误时方案为空
    批复 = 生成批复(方案["添加"], 方案["删除"], 错误)
    with open(方案文件名, "w", encoding="utf-8") as f:
        json.dump(方案, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    with open(批复文件名, "w", encoding="utf-8") as f:
        f.write(批复 + "\n")
    if 错误 or not (方案["添加"] or 方案["删除"]):
        print("驳回：所呈格式有误或空空如也，批复已写入 %s" % 批复文件名, file=sys.stderr)
        return 1
    print("准予：方案已写入 %s，批复已写入 %s" % (方案文件名, 批复文件名))
    return 0


def 应用方案(方案路径):
    """把方案应用到 terms/contrib.json（不存在则创建），仅动此文件。

    添加 = 写入/覆盖；删除 = 移除存在的 key（不存在不报错）；
    先删除后添加，同词既删又添时以添加为准。
    输出保持 json.dump(ensure_ascii=False, indent=2, sort_keys=True) + 末尾换行。
    """
    with open(方案路径, encoding="utf-8") as f:
        方案 = json.load(f)
    添加 = 方案.get("添加", {}) if isinstance(方案, dict) else {}
    删除 = 方案.get("删除", []) if isinstance(方案, dict) else []
    贡献词库 = {}
    if os.path.exists(贡献词库文件):
        try:
            with open(贡献词库文件, encoding="utf-8") as f:
                数据 = json.load(f)
            if isinstance(数据, dict):
                贡献词库 = 数据
        except (OSError, ValueError):
            贡献词库 = {}
    for 原词 in 删除:
        贡献词库.pop(str(原词).strip().lower(), None)
    for 原词, 译名 in 添加.items():
        贡献词库[str(原词).strip().lower()] = str(译名).strip()
    with open(贡献词库文件, "w", encoding="utf-8") as f:
        json.dump(贡献词库, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("%s: %d 条" % (贡献词库文件, len(贡献词库)))


def 解析参数(参数列表):
    解析器 = argparse.ArgumentParser(description="词库呈批：解析呈批 issue 正文、生成批复，并应用方案到贡献词库")
    解析器.add_argument("--校验", dest="校验", metavar="正文文件", default=None,
                       help="解析呈批正文，输出 呈批方案.json 与 批复.md（驳回时退出码非零）")
    解析器.add_argument("--应用", dest="应用", metavar="方案文件", default=None,
                       help="把方案应用到 terms/contrib.json")
    return 解析器.parse_args(参数列表)


def 主程序(参数列表=None):
    参数 = 解析参数(参数列表 if 参数列表 is not None else sys.argv[1:])
    if 参数.校验 is not None:
        return 校验主流程(读正文(参数.校验))
    if 参数.应用 is not None:
        应用方案(参数.应用)
        return 0
    print("用法: 词库呈批.py --校验 正文文件 / --应用 方案文件", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(主程序())
