# 话语权翻译机 · 设计文档

一个整活翻译工具：把文本里的英文术语**刻意**翻译成"官方定名 / 直译腔"中文。

灵感来源：token → 词元。范例风格（验收标准即此）：

> 我启动了**视窗十一操作系统**，打开桌面上已经更名为**聊天生成式预训练转换器**的**代码叉**，正想选择**生成式预训练转换器第五点六代太阳版**，结果发现本周的**词元**已用尽。无奈启动了**微软大战代码**……

## 核心原则

- **中文句子一个字不动**，只把英文术语抠出来逐个替换，保证输出通顺；
- **一个词只翻一次**：种子词典命中 → 直接用；未命中 → LLM 翻译 → 写入术语级缓存；
- **缓存即词典**：cache.json 越用越全，常见词最终离线可查。

## 流水线

```
中英混合输入
  │ ① 切分：正则抠出英文段（含多词术语、C++/C#/.NET/GPT-5.6/base_url 等）
  │ ② 种子词典 terms/seed.json：大小写不敏感、最长匹配优先
  │ ③ 未命中词/段 → 批量打包，一次 LLM 调用，返回 JSON 映射
  │ ④ 写入 cache.json（启动时加载，与词典合并）
  │ ⑤ 原样回填，直接替换不加空格，中文与其他字符原封不动
```

## 切分算法（Python 与 JS 实现必须一致）

1. 用正则 `[A-Za-z0-9]+(?:[ \t.+#_-][A-Za-z0-9]+)*` 捕获"英文段"，
   允许段内以单个空格或符号连接：`Windows 11`、`Visual Studio Code`、`C++`、`base_url`、`GPT-5.6`。
2. 对每个英文段，先**整段**查词典（key 统一小写比较）。
3. 整段未命中 → 段内从左到右做**最长匹配**切分（词典 + 缓存合查），
   切不出的连续残余收为"未知词"。
4. 所有未知词/段收集去重后，**一次批量调用** LLM，返回 `{原词: 译名}` JSON，并入缓存。
5. 回填：译名原位替换，不加任何空格。

## 翻译模式

- **模式 A（默认，主打）**：中英混合输入 → 只换英文术语 → 通顺官腔文。
- **模式 B（`--mode b`，可选）**：纯英文输入 → 按空格逐词硬翻（标点保留）→ 塑料中文腔。

## LLM 提示词风格规则（写进 system prompt）

1. 有官方定名的优先用定名：token→词元、agent→智能体、prompt→提示词；
2. 缩写先展开全称再逐字硬翻：API→应用程序编程接口、ChatGPT→聊天生成式预训练转换器、LLM→大语言模型；
3. 普通词字面直译：Python→蟒蛇、Java→爪哇、cookie→小甜饼、bug→虫子；
4. 品牌名用官方中文名或恶搞音意译：Microsoft→微软、Codex→代码叉、Copilot→大战代码、DeepSeek→深度求索；
5. 阿拉伯数字一律译为语文数字并附大写（零壹贰弎肆伍陆柒捌玖拾）：11→十一（壹拾壹）、5.6→五点六（伍点陆）；版本号片段（可能带前导符号，如 -5.6、v2）忽略符号，译为"第X点Y代"并附大写；译名不得残留英文字母/阿拉伯数字；
6. 每个词只输出译名本身，一本正经，不解释、不加引号；
7. 附带 3~5 组 few-shot 示例；temperature=0；要求返回**严格 JSON 对象** `{"原词": "译名", ...}`。

## LLM 接口（llm.py）

- OpenAI 兼容 chat completions 接口，函数签名：`translate_terms(terms: list[str]) -> dict[str, str]`；
- 容错解析：从响应中提取第一个 JSON 对象；失败返回 `{}`，调用方保留原词；
- 环境变量（按优先级）：
  - API Key：`HYQ_API_KEY` → `DEEPSEEK_API_KEY` → `OPENAI_API_KEY`
  - Base URL：`HYQ_BASE_URL` → 默认 `https://api.deepseek.com`
  - 模型：`HYQ_MODEL` → 默认 `deepseek-chat`
- 只依赖 Python 标准库（urllib），不引入第三方包。

## CLI（translate.py）

```
python3 translate.py "要翻译的文本"
python3 translate.py --file input.txt
cat input.txt | python3 translate.py
选项：
  --mode a|b    翻译模式，默认 a
  --no-llm      离线模式：只用词典+缓存，未命中词保持原样
```

## 文件结构

```
tech_project/
├── DESIGN.md           # 本文档
├── README.md           # 使用说明（中文）
├── terms/
│   └── seed.json       # 种子词典（手工维护的经典译名）
├── cache.json          # 术语级缓存（运行时自动生成，格式同 seed.json）
├── translate.py        # CLI 主程序：切分/查词典/调LLM/缓存/回填
├── llm.py              # LLM 调用封装（OpenAI 兼容，仅标准库）
├── build_web_dict.py   # 合并 terms/seed.json + cache.json → terms.js
└── index.html          # 网页版：单文件应用，无外部依赖
```

## 词典格式（seed.json 与 cache.json 相同）

扁平 JSON 对象，key 一律**小写英文**，value 为中文译名：

```json
{
  "token": "词元",
  "tokens": "词元",
  "api": "应用程序编程接口",
  "windows 11": "视窗十一操作系统"
}
```

### 种子词典必含条目（不得遗漏）

token/tokens→词元、api→应用程序编程接口、api key→应用编程接口秘钥、
base_url/base url→请求地址、chatgpt→聊天生成式预训练转换器、
gpt→生成式预训练转换器、codex→代码叉、copilot→大战代码、
microsoft copilot→微软大战代码、microsoft→微软、deepseek→深度求索、
deepseek-v4-flash→深度求索模型第四代闪光版、python→蟒蛇、
windows 11→视窗十一操作系统、windows→视窗、prompt→提示词、
agent→智能体、llm→大语言模型、solar→太阳版。
其余按风格规则自由扩展到 80~120 条，覆盖四类：AI 大模型 / 操作系统与科技大厂 /
编程语言与开发工具 / 互联网与数字生活。

## 网页版（index.html）

- 单文件、零外部依赖（不用任何 CDN/框架），`<script src="terms.js"></script>` 读 `window.TERMS`；
- terms.js 缺失时给出提示"请先运行 python3 build_web_dict.py"；
- 实现与上面一致的切分 + 最长匹配逻辑（JS 版），输入框实时输出译文；
- BYOK 区域（可折叠）：用户填 API Key / Base URL / Model，前端直连 OpenAI 兼容接口，
  批量翻译未命中词，结果并入当前会话词典，可导出为 cache.json 下载；
- 标题"话语权翻译机"，内置验收例句作为示例按钮，界面简洁美观。

## 验收标准

输入（模式 A）：

```
我启动了 Windows 11，打开桌面上已经更名为 ChatGPT 的 Codex，正想选择 GPT-5.6 Solar，
结果发现本周的 token 已用尽。无奈启动了 Microsoft Copilot，把供应商调整为第三方的 DeepSeek。
我首先检查了 API base_url 和 API key 是否正常，然后确认模型是 DeepSeek-V4-Flash，
最后保存，编写了一些 Python 代码，然后愉快地消耗了两千万 token。
```

- `--no-llm` 模式下：种子词典覆盖的词全部正确替换，中文部分一字不变；
- 联网模式下：`GPT-5.6 Solar` 等未命中词由 LLM 补译为"生成式预训练转换器第五点六代太阳版"风格；
- 第二次运行同一输入：不产生 LLM 调用（全部命中缓存）。
