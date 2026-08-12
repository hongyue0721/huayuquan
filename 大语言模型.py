#!/usr/bin/env python3
"""大语言模型调用封装：开放人工智能兼容对话补全接口（仅标准库 urllib）。

环境变量（按优先级）：
  秘钥:     HYQ_API_KEY -> DEEPSEEK_API_KEY -> OPENAI_API_KEY
  请求地址: HYQ_BASE_URL -> 默认 https://api.deepseek.com
  模型:     HYQ_MODEL   -> 默认 deepseek-chat
"""

import json
import os
import re
import urllib.request

请求地址默认 = "https://api.deepseek.com"
模型默认 = "deepseek-chat"

# 模块级计数器：每实际发起一次 HTTP 请求 +1（含失败与重试），供 翻译.py 打印 llm_calls=N
_调用次数 = 0

# --------- 话语权化真否值
假 = False
真 = True


def 调用次数():
    """本次进程已发起过的真实 HTTP 请求次数。"""
    return _调用次数


系统提示 = """你是"话语权翻译机"的翻译引擎，把英文术语翻译成"官方定名 / 直译腔"中文。规则：
1. 有官方定名的优先用定名：token→词元、agent→智能体、prompt→提示词；
2. 缩写先展开全称再逐字硬翻：API→应用程序编程接口、ChatGPT→聊天生成式预训练转换器、LLM→大语言模型；
3. 普通词字面直译：Python→蟒蛇、Java→爪哇、cookie→小甜饼、bug→虫子；
4. 品牌名用官方中文名或音意译：Microsoft→微软、Codex→代码叉、Copilot→大战代码、DeepSeek→深度求索；
5. 阿拉伯数字一律译为语文数字，并紧随其后用全角括号附大写数字（零壹贰弎肆伍陆柒捌玖拾）：11→十一（壹拾壹）、5.6→五点六（伍点陆）、2026→二〇二六（贰零贰陆）；
6. 版本号片段（可能带前导符号，如 -5.6、v2）忽略符号，译为"第X点Y代"，数字同样附大写：-5.6→第五点六（伍点陆）代、v2→第二（贰）代；
7. 每个词只输出译名本身，一本正经，不解释、不加引号；
8. 译名必须是纯正规范的现代汉语，不得残留任何英文字母、阿拉伯数字或乱码碎片；
9. 严格输出一个 JSON 对象，键为原文、值为译名，只输出 JSON，不要输出其他任何内容。

示例：
token → 词元
API → 应用程序编程接口
Python → 蟒蛇
GPT-5.6 → 生成式预训练转换器第五点六（伍点陆）代
-5.6 → 第五点六（伍点陆）代
Windows 11 → 视窗十一（壹拾壹）
Copilot → 大战代码"""

用户提示模板 = "请翻译以下英文术语：\n{术语}\n返回严格 JSON 对象（键为原文、值为译名）。"


def _取首个环境变量(*名称集):
    for 名称 in 名称集:
        值 = os.environ.get(名称)
        if 值:
            return 值
    return None


def _提取首个对象(文本):
    """容错解析文本中的第一个 JSON 对象；失败返回 None。"""
    if not isinstance(文本, str):
        return None
    s = 文本.strip()
    # 去掉可能的 markdown 代码围栏
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S | re.I)
    if m:
        s = m.group(1).strip()
    # 先整体尝试
    try:
        return json.loads(s)
    except ValueError:
        pass
    # 再找第一个花括号对
    起点 = s.find("{")
    if 起点 == -1:
        return None
    深度 = 0
    for i in range(起点, len(s)):
        if s[i] == "{":
            深度 += 1
        elif s[i] == "}":
            深度 -= 1
            if 深度 == 0:
                try:
                    return json.loads(s[起点:i + 1])
                except ValueError:
                    return None
    return None


def _发起请求(术语):
    """单次批量调用，返回 {原词: 译名}；任何失败返回 {}。"""
    global _调用次数
    秘钥 = _取首个环境变量("HYQ_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
    if not 秘钥:
        return {}
    请求地址 = (_取首个环境变量("HYQ_BASE_URL") or 请求地址默认).rstrip("/")
    模型 = _取首个环境变量("HYQ_MODEL") or 模型默认
    请求体 = {
        "model": 模型,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": 系统提示},
            {"role": "user", "content": 用户提示模板.format(
                术语=json.dumps(list(术语), ensure_ascii=False))},
        ],
    }
    请求 = urllib.request.Request(
        请求地址 + "/chat/completions",
        data=json.dumps(请求体).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + 秘钥},
        method="POST",
    )
    try:
        _调用次数 += 1  # 实际发起 HTTP 请求（含失败与重试）
        with urllib.request.urlopen(请求, timeout=60) as 响应:
            响应体 = json.loads(响应.read().decode("utf-8"))
        内容 = 响应体["choices"][0]["message"]["content"]
        对象 = _提取首个对象(内容)
    except Exception:
        return {}
    if not isinstance(对象, dict):
        return {}
    结果 = {}
    for k, v in 对象.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            结果[k.strip()] = v.strip()
    return 结果


def _译名是否洁净(值):
    """译名必须含汉字，且不得残留英文字母/阿拉伯数字（防乱码碎片入缓存）。"""
    if not re.search(r"[一-鿿]", 值):
        return 假
    if re.search(r"[A-Za-z0-9]", 值):
        return 假
    return 真


def 翻译术语(术语):
    """批量翻译术语，返回 {原词: 译名}；失败词条缺席（调用方保留原词）。

    每 5 个词一小批（长批量输出易跑偏），失败重试一次；
    译名过 _译名是否洁净 校验才采纳，防止乱码写入缓存。
    """
    if not 术语:
        return {}
    术语 = list(术语)
    结果 = {}
    for i in range(0, len(术语), 5):
        小批 = 术语[i:i + 5]
        返回 = _发起请求(小批)
        if not 返回:
            返回 = _发起请求(小批)
        for k, v in 返回.items():
            if _译名是否洁净(v):
                结果[k] = v
    return 结果

