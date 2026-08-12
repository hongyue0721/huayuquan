#!/usr/bin/env python3
"""LLM 调用封装：OpenAI 兼容 chat completions（仅标准库 urllib）。

环境变量（按优先级）：
  API Key:  HYQ_API_KEY -> DEEPSEEK_API_KEY -> OPENAI_API_KEY
  Base URL: HYQ_BASE_URL -> 默认 https://api.deepseek.com
  模型:     HYQ_MODEL   -> 默认 deepseek-chat
"""

import json
import os
import re
import urllib.request

BASE_URL_DEFAULT = "https://api.deepseek.com"
MODEL_DEFAULT = "deepseek-chat"

SYSTEM_PROMPT = """你是"话语权翻译机"的翻译引擎，把英文术语翻译成"官方定名 / 直译腔"中文。规则：
1. 有官方定名的优先用定名：token→词元、agent→智能体、prompt→提示词；
2. 缩写先展开全称再逐字硬翻：API→应用程序编程接口、ChatGPT→聊天生成式预训练转换器、LLM→大语言模型；
3. 普通词字面直译：Python→蟒蛇、Java→爪哇、cookie→小甜饼、bug→虫子；
4. 品牌名用官方中文名或恶搞音意译：Microsoft→微软、Codex→代码叉、Copilot→大战代码、DeepSeek→深度求索；
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

USER_PROMPT_TMPL = "请翻译以下英文术语：\n{terms}\n返回严格 JSON 对象（键为原文、值为译名）。"


def _first_env(*names):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def _extract_first_json(text):
    """容错解析文本中的第一个 JSON 对象；失败返回 None。"""
    if not isinstance(text, str):
        return None
    s = text.strip()
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
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except ValueError:
                    return None
    return None


def _post_chat(terms):
    """单次批量调用，返回 {原词: 译名}；任何失败返回 {}。"""
    api_key = _first_env("HYQ_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        return {}
    base_url = (_first_env("HYQ_BASE_URL") or BASE_URL_DEFAULT).rstrip("/")
    model = _first_env("HYQ_MODEL") or MODEL_DEFAULT
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TMPL.format(
                terms=json.dumps(list(terms), ensure_ascii=False))},
        ],
    }
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        obj = _extract_first_json(content)
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    result = {}
    for k, v in obj.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            result[k.strip()] = v.strip()
    return result


def _is_clean_translation(v):
    """译名必须含汉字，且不得残留英文字母/阿拉伯数字（防乱码碎片入缓存）。"""
    if not re.search(r"[一-鿿]", v):
        return False
    if re.search(r"[A-Za-z0-9]", v):
        return False
    return True


def translate_terms(terms):
    """批量翻译术语，返回 {原词: 译名}；失败词条缺席（调用方保留原词）。

    每 5 个词一小批（长批量输出易跑偏），失败重试一次；
    译名过 _is_clean_translation 校验才采纳，防止乱码写入缓存。
    """
    if not terms:
        return {}
    terms = list(terms)
    result = {}
    for i in range(0, len(terms), 5):
        chunk = terms[i:i + 5]
        got = _post_chat(chunk)
        if not got:
            got = _post_chat(chunk)
        for k, v in got.items():
            if _is_clean_translation(v):
                result[k] = v
    return result
