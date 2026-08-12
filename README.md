# 话语权翻译机

一个整活翻译工具：把文本里的英文术语**刻意**翻译成"官方定名 / 直译腔"中文，中文部分原样保留。

灵感来源：token → 词元。

## 效果示例

以下输入来自 `DESIGN.md` 的验收例句（模式 A）：

```
我启动了 Windows 11，打开桌面上已经更名为 ChatGPT 的 Codex，正想选择 GPT-5.6 Solar，
结果发现本周的 token 已用尽。无奈启动了 Microsoft Copilot，把供应商调整为第三方的 DeepSeek。
我首先检查了 API base_url 和 API key 是否正常，然后确认模型是 DeepSeek-V4-Flash，
最后保存，编写了一些 Python 代码，然后愉快地消耗了两千万 token。
```

联网模式下，预期输出风格如下（示意；个别未命中词由 LLM 补译，可能略有出入）：

```
我启动了视窗十一操作系统，打开桌面上已经更名为聊天生成式预训练转换器的代码叉，正想选择生成式预训练转换器第五点六代太阳版，
结果发现本周的词元已用尽。无奈启动了微软大战代码，把供应商调整为第三方的深度求索。
我首先检查了应用程序编程接口请求地址和应用程序编程接口秘钥是否正常，然后确认模型是深度求索模型第四代闪光版，
最后保存，编写了一些蟒蛇代码，然后愉快地消耗了两千万词元。
```

验收要点：

- `--no-llm` 模式下：种子词典覆盖的词全部正确替换，中文部分一字不变；
- 联网模式下：`GPT-5.6 Solar` 等未命中词由 LLM 补译为"生成式预训练转换器第五点六代太阳版"风格；
- 第二次运行同一输入：不产生 LLM 调用（全部命中缓存）。

## 文件结构

```
tech_project/
├── DESIGN.md           # 设计文档
├── README.md           # 使用说明（本文档）
├── terms/
│   └── seed.json       # 种子词典（手工维护的经典译名）
├── cache.json          # 术语级缓存（运行时自动生成，格式同 seed.json）
├── translate.py        # CLI 主程序：切分/查词典/调LLM/缓存/回填
├── llm.py              # LLM 调用封装（OpenAI 兼容，仅标准库）
├── build_web_dict.py   # 合并 terms/seed.json + cache.json → terms.js
└── index.html          # 网页版：单文件应用，无外部依赖
```

## CLI 用法

```bash
# 命令行直接传参（模式 A，默认）
python3 translate.py "要翻译的文本"

# 从文件读取
python3 translate.py --file input.txt

# 从标准输入读取
cat input.txt | python3 translate.py
```

选项：

| 选项 | 说明 |
| --- | --- |
| `--mode a\|b` | 翻译模式，默认 `a`。模式 A：中英混合输入，只换英文术语，产出通顺官腔文；模式 B：纯英文输入，按空格逐词硬翻（标点保留），产出塑料中文腔 |
| `--no-llm` | 离线模式：只用词典 + 缓存，未命中词保持原样 |

## 网页版用法

网页版名为「话语权掌握器」，单文件应用、零外部依赖，无需服务器：

1. 先运行 `python3 build_web_dict.py` 合并词典，生成 `terms.js`（合并 `terms/seed.json` + `cache.json`）；
2. 直接用浏览器打开 `index.html`；
3. 在输入框粘贴原文，点击「点击掌握话语权」按钮翻译。

- 网页版实现与 CLI 一致的切分 + 最长匹配逻辑（JS 版），输入框实时输出译文；
- 若 `terms.js` 缺失，页面会提示"请先运行 python3 build_web_dict.py"；
- **BYOK（Bring Your Own Key）**：页面内置可折叠的 BYOK 区域，自行填入 API Key / Base URL / Model，前端直连 OpenAI 兼容接口批量翻译未命中词，结果并入当前会话词典，可导出为 `cache.json` 下载。

## 后台赋能（GitHub Actions 托管）

不想自己跑 Python？仓库内置 GitHub Actions 工作流 `.github/workflows/empower.yml`，在 GitHub 上即可完成翻译与计数：

1. **部署者配置密钥**：在仓库 **Settings → Secrets and variables → Actions** 新建三个 secret：`HYQ_API_KEY`（必填）、`HYQ_BASE_URL`（可选，默认 `https://api.deepseek.com`）、`HYQ_MODEL`（可选，默认 `deepseek-chat`）；
2. **用户使用**：在 Issues 里新建一个标题含「翻译请求」的 issue，把原文粘贴到正文并提交即可。Actions 会自动用 `translate.py` 翻译，并以评论形式把结果回复到该 issue，同时把 `counters.json` 里的 `translations` 字段累加 1，即「技术突破与文化自信双向赋能次数」；
3. **GitHub Pages 部署**：仓库 **Settings → Pages** → Source 选「Deploy from a branch」→ 分支选默认分支、目录选「/(root)」→ Save，即可通过 `https://<用户名>.github.io/<仓库名>/` 访问网页版「话语权掌握器」。

> **密钥安全**：该架构下 `HYQ_API_KEY` 等只存在于仓库 Secrets 中，前端页面与仓库代码里均不出现任何密钥；Actions 仅在运行时通过 `secrets.HYQ_*` 注入临时环境变量，翻译结束即丢弃。

## 环境变量配置

LLM 调用为 OpenAI 兼容接口，仅依赖 Python 标准库（urllib），无需安装任何第三方包。环境变量按优先级读取：

| 变量 | 优先级 / 默认值 |
| --- | --- |
| `HYQ_API_KEY` | 最高优先级 |
| `DEEPSEEK_API_KEY` | 次之 |
| `OPENAI_API_KEY` | 兜底 |
| `HYQ_BASE_URL` | 默认 `https://api.deepseek.com` |
| `HYQ_MODEL` | 默认 `deepseek-chat` |

示例：

```bash
export HYQ_API_KEY="sk-xxx"
export HYQ_BASE_URL="https://api.deepseek.com"
export HYQ_MODEL="deepseek-chat"
python3 translate.py "我启动了 Windows 11"
```

## 词典与缓存机制

- **缓存即词典**：`cache.json` 是运行时自动生成的术语级缓存，格式与 `terms/seed.json` 完全相同，启动时加载并与种子词典合并；
- **越用越全**：每次未命中的词经 LLM 翻译后都会写入缓存，常见词最终离线可查，联网依赖逐步降低；
- **第二次运行同一输入零 LLM 调用**：同一次输入中的全部术语在第一次运行后已入缓存，第二次运行全程命中，不再发起任何 LLM 请求。

工作流程：正则切分出英文段 → 种子词典 + 缓存查词（小写比较、最长匹配优先）→ 未命中词批量打包，一次 LLM 调用 → 写入缓存 → 原样回填，不加任何空格。

## 向 terms/seed.json 贡献新词条

`terms/seed.json` 是手工维护的种子词典，格式为扁平 JSON 对象：

- key 一律**小写英文**（多词用空格分隔，如 `"windows 11"`、`"base_url"` 按原文书写）；
- value 为中文译名，直接输出译名本身，不解释、不加引号。

```json
{
  "token": "词元",
  "tokens": "词元",
  "api": "应用程序编程接口",
  "windows 11": "视窗十一操作系统"
}
```

新增词条请遵循以下五条风格规则：

1. **有官方定名优先用定名**：token→词元、agent→智能体、prompt→提示词；
2. **缩写先展开全称再逐字硬翻**：API→应用程序编程接口、ChatGPT→聊天生成式预训练转换器、LLM→大语言模型；
3. **普通词字面直译**：Python→蟒蛇、Java→爪哇、cookie→小甜饼、bug→虫子；
4. **品牌名用官方中文名或恶搞音意译**：Microsoft→微软、Codex→代码叉、Copilot→大战代码、DeepSeek→深度求索；
5. **阿拉伯数字一律译为语文数字并附大写**（零壹贰弎肆伍陆柒捌玖拾）：11→十一（壹拾壹）、5.6→五点六（伍点陆）；版本号片段忽略前导符号，译为"第X点Y代"并附大写；译名不得残留英文字母/阿拉伯数字。

## 免责声明

本软件每次联网翻译都在真实消耗词元，请珍惜使用。
