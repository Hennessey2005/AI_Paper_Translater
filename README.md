# AI_Paper_Translater

**PDF 学术论文 → 深度理解包**：一条命令产出「中文译文 + LaTeX 公式注册表 + 图表内容描述」，面向个人知识库 / Agent RAG 场景。

## 功能

| 痛点 | 方案 | 产出 |
|---|---|---|
| 公式变乱码 / 被翻译毁掉 | 公式剥离为 LaTeX + 占位符保护 + 语法回验 | `formulas/` |
| 图表只是图片，无法检索 | 多模态模型生成中文描述 + 数据表 | `figures/` |
| 译文无法进知识库 | 语义块翻译 + 页码/坐标溯源层 | `译文.zh.md` + `segments.json` |

## 工作原理

```
PDF ─► S1 MinerU解析 ─► S2 公式剥离 ─► S3 图表理解 ─► S4 翻译 ─► S5 组装
        (CPU 本地)       (CPU 本地)     (VLM API)    (LLM API)   (本地)
```

版面/OCR/公式/表格识别全部 CPU 本地运行（MinerU basic 档）；仅图表理解与翻译调用 API；有本地 GPU 时可整体升级。

## 快速开始

### Windows（推荐：自动配置 + 拖拽）

```bash
git clone git@github.com:Hennessey2005/AI_Paper_Translater.git
```

打开仓库目录，**把 PDF 拖到 `run.bat` 图标上**（支持一次拖多个；也可双击后把文件拖入窗口回车）。首次运行自动完成：缺 Python 则引导安装 → 建 venv 装依赖 → 记事本打开 `config\config.yaml` 引导填 API key，之后秒进。处理完成后自动打开结果目录。

### 手动 / 其他平台

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -e .

copy config\config.example.yaml config\config.yaml  # 填入你的 API key（已 gitignore）
paper-translate paper.pdf
```

常用参数：

```bash
paper-translate paper.pdf --offline                       # 仅本地阶段，不调 API
paper-translate paper.pdf --cache-dir output/_cache/<hash> # 复用解析缓存
paper-translate paper.pdf --open                          # 完成后打开输出目录
python -m paper_translate paper.pdf                        # 未安装命令时
```

默认适配硅基流动（OpenAI 兼容协议），图表理解 `Qwen/Qwen3-VL-32B-Instruct`、翻译 `DeepSeek-V4.1-Flash`，换平台只需改 `base_url` 和模型名。

## 输出结构

```
output/<论文标题>/
├── 译文.zh.md          # 中文译文（公式 LaTeX 内嵌、图表原位描述）
├── 译文.bilingual.md   # 中英对照
├── formulas/           # 公式注册表（编号/页码/LaTeX/回验状态）
├── figures/            # 图表理解（图注译文/VLM 描述/数据表）
├── segments.json       # 溯源层：译文段 ↔ PDF 页码/坐标
└── _cache/             # 缓存（断点续跑不重复计费）
```

输出目录自动以 **PDF 内的论文真实标题**命名（取自解析结果，纯本地；标题非法字符自动清洗、超 80 字符截断；同名论文以内容哈希后缀区分，同篇重跑复用目录），也可用 `-o` 指定。

## 实测指标（双栏 5 页 arXiv 论文，纯 CPU）

全流程约 **13 分钟 / < ¥0.5**：解析 9.5 min（免费）+ 图表理解 ~5k tokens + 翻译 ~27k tokens；公式与 LaTeX 源码对照 0 错误；缓存命中后重跑 0 次 API 调用。

## 项目结构

```
src/paper_translate/   # cli / orchestrator / S2-S5 阶段模块 / VLM+LLM 客户端
scripts/               # M1-M4 阶段回归测试 + 模型选型对比
config/                # 配置模板 + 术语表（可积累）
```

## 致谢

[MinerU](https://github.com/opendatalab/MinerU) · [硅基流动](https://siliconflow.cn)
