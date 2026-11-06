# my-jewelry-renderer

把**一件珠宝设计**批量渲染成**多材质 × 多宝石 × 多视角**的成品效果图，并给出一张可对账的清单。
面向出图量大、需要反复改款、需要逐张核对素材的场景（电商详情页、选款册、客户看款、广告素材）。

一条命令、一份 YAML，就能把「设计稿」摊开成几十上百张风格统一的产品图。

## 它做三件事

1. **展开矩阵**：`金属 × 宝石 × 视角 × 变体` 自动笛卡尔积，任务编号稳定（同配置同顺序 → 同文件名），不会跑乱。
2. **批量出图**：多线程并发调用图像模型，退避重试，失败的只重试失败的那张。
3. **对账校验**：`manifest.csv` 记录每张图的状态、耗时、重试次数、后端与完整提示词；`report` 会反过来校验"清单说成功、文件却不在/小于 1KB"这类漂移。

## 安装

```bash
git clone https://github.com/tiffanyeastarts-sys/my-jewelry-renderer.git
cd my-jewelry-renderer
pip install -r requirements.txt
```

## 三步跑通

```bash
# 1) 先看要出多少张、每张的提示词长什么样（不花钱、不调 API）
python -m jrenderer plan -c configs/ring.yaml --prompts prompts.txt

# 2) 试跑两张（--limit 2），用程序化占位后端验证链路
python -m jrenderer render -c configs/ring.yaml --provider mock --limit 2

# 3) 换真实模型，整批出图
export ARK_API_KEY=你的key
python -m jrenderer render -c configs/ring.yaml --provider ark --workers 4

# 4) 校验并汇总
python -m jrenderer report --dir output/光环六爪钻戒
```

## 后端

| provider | 用途 | 需要的环境变量 |
| --- | --- | --- |
| `ark` | 火山方舟 / 豆包 Seedream，支持传入参考图（图生图） | `ARK_API_KEY`，可选 `ARK_IMAGE_MODEL`、`ARK_BASE_URL` |
| `openai` | 任何 OpenAI 兼容的 `/images/generations`（自建 SD、中转、DashScope 兼容层） | `IMAGE_API_BASE`、`IMAGE_API_KEY`，可选 `IMAGE_API_MODEL` |
| `mock` | 离线程序化占位图（Pillow 绘制），只用来验证管线 | 无 |

`ark` 的默认模型是 `doubao-seedream-4-0-250828`，可用 `--model` 或 `ARK_IMAGE_MODEL` 覆盖。
参考图可以是 URL，也可以是本地文件路径（会自动转成 data URL）。

## 配置字段

```yaml
piece:
  name: "光环六爪钻戒"          # 单品名，同时是输出子目录名
  description: "六爪镶嵌…"      # 主体描述：结构、镶嵌方式、细节工艺
  style: "…"                   # 可选，摄影风格；不填用内置珠宝摄影风格
  background: "…"              # 可选，背景描述；不填用内置浅灰渐变
  extra_prompt: "…"            # 可选，追加到每条提示词末尾的补充约束
  reference_image: "ref.png"   # 可选，参考图（URL 或本地路径），用于图生图
metals:  [yellow_gold, white_gold, rose_gold, platinum]
gems:    [round_brilliant, {key: oval_sapphire, zh: 椭圆形切割皇家蓝蓝宝石}]
angles:  [front, top45, side, macro_detail]
variants_per_combo: 1           # 每个组合出几张（同一提示词多取几次，取不同的随机结果）
size: "2048x2048"               # 传给后端的分辨率
ratio: "1:1"                    # 记录用，便于下游裁切
out_dir: "output"
```

- **金属**：`yellow_gold` `white_gold` `rose_gold` `platinum` `black_rhodium`
- **宝石**：`round_brilliant` `emerald_cut` `oval_sapphire` `ruby` `emerald` `pearl` `aquamarine`
- **视角**：`front` `top45` `side` `macro_detail`

词表在 `jrenderer/vocab.py`，新增一种材质/宝石只要加一项 dict（含中英文名、描述、占位图颜色），整条矩阵立即生效。
单条宝石写成 dict 时可以覆盖 `zh` / `en` / `hint`，用来描述这一批特有的宝石（例如某批货是皇家蓝、某批是矢车菊蓝）。

## 断点续跑与失败重试

- 本地已存在且大于 1KB 的同名文件，默认跳过（`skipped`），只补跑缺的；`--force` 全部重跑。
- 429 / 5xx / 网络错误自动退避重试（`--retries` 次数、`--backoff` 基数秒）；4xx 这类不可恢复错误直接记失败，不浪费时间重试。
- 文件先写 `.part` 再原子替换，中断不会留下半截图。
- 任何单任务异常都被拦在任务内，不会拖垮整批。

## 产物结构

```
output/光环六爪钻戒/
├── 光环六爪钻戒__yellow_gold__round_brilliant__front__v1.png
├── 光环六爪钻戒__white_gold__oval_sapphire__top45__v1.png
└── manifest.csv      # 每张图的状态/耗时/重试/后端/模型/完整提示词
```

文件名本身可读：`单品__金属__宝石__视角__变体.png`，下游按文件名就能筛出想要的子集。

## 自测

```bash
python -m unittest discover -s tests -v
```

9 项离线测试，不联网、不需要 Key：矩阵展开与重名检查、坏配置报错、可重试错误退避后成功、
不可恢复错误不浪费重试、续跑不篡改已成功记录、参考图 data URL 转换。

> 示例占位图不随仓库提交（二进制不适合这个通道）。想看版式效果，用 mock 后端跑一遍即可：
> `python -m jrenderer render -c configs/quickstart.yaml --provider mock`

## 直接当 Python 库用

```python
from jrenderer.spec import load_spec
from jrenderer.providers import get_provider
from jrenderer.runner import run

spec = load_spec("configs/ring.yaml")
provider = get_provider("ark")
run(spec, provider, workers=6, limit=10)
```

## 目录

```
jrenderer/
├── vocab.py            材质/宝石/视角词表 + 提示词构建
├── spec.py             YAML 解析、参数校验、矩阵展开
├── runner.py           并发、重试、续跑、manifest
├── cli.py              plan / render / report
└── providers/          ark / openai 兼容 / mock
configs/                ring.yaml、pendant.yaml、quickstart.yaml
tests/                  9 项离线自测（重试、续跑、校验、错误路径）
```
