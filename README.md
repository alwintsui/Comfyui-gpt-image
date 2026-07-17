# Comfyui-Luck gpt-2.0

OpenAI GPT 图像模型的 ComfyUI 自定义节点包，当前包含出图节点和提示词控制节点：

> **重要说明**
>
> 本自定义节点支持原生OpenAI key或者上游代理key访问，当前默认使用gpt-image-2图像模型。本项目从Comfyui-Luck-gpt2.0 [GitHub Issues](https://github.com/luckdvr/Comfyui-Luck-gpt2.0/issues) 修改而来，删除ComfyuiLuckGPTImage2VipNode节点（Comfyui-Luck gpt-image-2-vip），增加了首先从环境变量OPENAI_BASE_URL和OPENAI_API_KEY中读取base-url和api-key的取值，base-url提供可选值列表，api-key可以从节点属性输入，并且提供隐藏功能，注意导出分享工作流需要把API key清空。

| 节点 | 模型 | 适合场景 | 尺寸控制 |
|---|---|---|---|
| `Comfyui-Luck gpt-image-2` | `gpt-image-2` | 需要真实 size、2K/4K、自定义尺寸、quality、mask | 真正传 `size` API 参数 |

| 提示词节点 | 默认模型 | 适合场景 |
|---|---|---|
| `GPT-Image-2 文生图提示词控制器` | `gemini-3.5-flash` | 将文字需求整理为更适合 GPT-Image-2 的结构化生图提示词 |
| `图生图提示词控制器` | `gemini-3.5-flash` | 读取最多 5 张参考图和可选主体图，生成带风格、构图、版式约束的出图提示词 |
| `文本停留编辑器` | - | 工作流执行中暂停，手动编辑文本后继续 |

提示词控制器使用 API易 OpenAI 兼容 `POST /v1/chat/completions`，和 Luck 出图节点一样使用 `Authorization: Bearer YOUR_API_KEY`。模型下拉包含 `gemini-3.5-flash`、`gpt-5.6`、`gpt-5.5`、`gpt-4o`、`gpt-4.1-mini`、`gemini-2.5-flash`、`gemini-2.5-pro`。

`图生图提示词控制器` 的 `reference_image_01` 必填，`reference_image_02` 到 `reference_image_05` 可选；多张参考图会一起发送给多模态模型综合分析。`subject_image` 仍然是可选主体图，用来锁定最终画面的核心产品或人物。

多图参考的推荐接法：

- 只把图片接到 `图生图提示词控制器`：只做图像理解和提示词增强，后面可以按文生图使用优化后的 prompt。
- 同一批图片同时接到后面的出图节点：才是真正的多图参考 / 多图编辑 / 多图融合。
- 5 张图以内，优先接 `图生图提示词控制器` 一起分析，再把同一批图接到后面的出图节点。
- `Comfyui-Luck gpt-image-2` 支持最多 16 张参考图，并支持真实 size、quality 和 mask。

完整链路示例：

```text
5张参考图
  ├─ 接到 图生图提示词控制器 reference_image_01~reference_image_05
  └─ 同时接到 Comfyui-Luck gpt-image-2 image_01~image_05

图生图提示词控制器 optimized_prompt
  └─ 接到 Comfyui-Luck gpt-image-2 prompt
```

如果其中一张图是必须锁定的主体图，可以额外接到 `subject_image`，并放在后面出图节点的 `image_01`。

暂停编辑后再出图的推荐接法：

```text
提示词控制器 optimized_prompt
  └─ 接到 文本停留编辑器 text_list

文本停留编辑器 edited_text
  └─ 接到 出图节点 prompt
```

`edited_text` 是单条字符串，适合接普通出图节点的 prompt。`edited_texts` 是列表输出，保留给批量文本工作流使用。

运行时请对最终 `PreviewImage` 或 `SaveImage` 发起队列执行。流程停在 `文本停留编辑器` 后，点击节点上的 `Continue` 即可让当前执行继续到后面的出图节点；不要再次点击主运行按钮，否则 ComfyUI 会重新排队并重新执行上游提示词增强。

## 安装

1. 把整个目录复制到 ComfyUI 的 `custom_nodes` 目录。
2. 安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

3. 重启 ComfyUI，搜索 `Comfyui-Luck`。

## 节点：Comfyui-Luck gpt-image-2

使用官方契约的 `gpt-image-2`。

特点：

- 真正传 `size` 参数，面板按 Nano 风格拆成 `image_size (分辨率)` + `aspect_ratio (宽高比)`。
- `quality`：`auto`、`low`、`medium`、`high`。
- `output_format`：`png`、`jpeg`、`webp`。
- `output_compression`：`jpeg` / `webp` 时可用，范围 0-100。
- 支持最多 16 张参考图。
- 支持可选 `mask` 局部重绘，透明区域 = 要重绘，不透明区域 = 保留。

尺寸换算：

| aspect_ratio | 1K | 2K | 4K |
|---|---:|---:|---:|
| `AUTO` | 不传 size | 不传 size | 不传 size |
| `1:4` | `480x1440` | `672x2016` | `1280x3840` |
| `4:1` | `1440x480` | `2016x672` | `3840x1280` |
| `1:8` | `480x1440` | `672x2016` | `1280x3840` |
| `8:1` | `1440x480` | `2016x672` | `3840x1280` |
| `1:1` | `1024x1024` | `2048x2048` | `2880x2880` |
| `1:2` | `720x1440` | `1024x2048` | `1920x3840` |
| `2:1` | `1440x720` | `2048x1024` | `3840x1920` |
| `1:3` | `480x1440` | `672x2016` | `1280x3840` |
| `3:1` | `1440x480` | `2016x672` | `3840x1280` |
| `2:3` | `768x1152` | `1440x2160` | `2304x3456` |
| `3:2` | `1152x768` | `2160x1440` | `3456x2304` |
| `3:4` | `768x1024` | `1536x2048` | `2448x3264` |
| `4:3` | `1024x768` | `2048x1536` | `3264x2448` |
| `4:5` | `768x960` | `1536x1920` | `2304x2880` |
| `5:4` | `960x768` | `1920x1536` | `2880x2304` |
| `9:16` | `720x1280` | `1152x2048` | `2160x3840` |
| `16:9` | `1280x720` | `2048x1152` | `3840x2160` |
| `9:21` | `640x1488` | `960x2240` | `1648x3840` |
| `21:9` | `1344x576` | `2464x1056` | `3808x1632` |

说明：

- `aspect_ratio` 列表和提示词控制器保持一致：`AUTO`、`1:4`、`4:1`、`1:8`、`8:1`、`1:1`、`1:2`、`2:1`、`1:3`、`3:1`、`2:3`、`3:2`、`3:4`、`4:3`、`4:5`、`5:4`、`9:16`、`16:9`、`9:21`、`21:9`。
- `auto (不传size)` 或 `aspect_ratio=AUTO` 会让 API 自适应。
- `gpt-image-2` 官方限制长边/短边 <= 3:1，所以 `1:4`、`4:1`、`1:8`、`8:1` 会自动收敛到最接近的合法边界尺寸，不会硬传非法比例。
- `4K` 档位尽量取合法大尺寸；`4K + 1:1` 不是 `3840x3840`，因为总像素会超官方上限，所以使用 `2880x2880`。
- 超过 `2560x1440` 总像素量的输出，官方提示属于实验性，可能更慢或更容易超时。

`custom_size` 只在 `image_size` 选择 `custom (自定义)` 时填写，格式如 `1600x1200`、`3072x1024`、`1024x3072`。选择 1K/2K/4K 时会忽略这个输入框。

`custom_size` 约束：

- 最大边 <= 3840px。
- 宽和高都是 16 的倍数。
- 长边/短边 <= 3:1，也就是说 3:1 和 1:3 都可以，超过不行。
- 总像素在 655,360 到 8,294,400 之间。

说明：

- `gpt-image-2` 返回的 `b64_json` 是纯 base64，不带 `data:image/...;base64,` 前缀；节点会自动解码成 ComfyUI 图片。
- 节点不会发送 `input_fidelity`。
- 节点主面板不再显示 `background` / `moderation`，默认不传，使用 API 默认值。
- 推荐超时按 `quality` 分档：`low` 至少 `120` 秒，`medium` 至少 `240` 秒，`high` 建议 `600` 秒起步；节点默认 `600` 秒。
- `408`、`429`、`5xx` 会按 `retry_times` 自动重试。`408 Timeout` 通常是 APIYi 上游生成任务超时，不是节点参数填错。

`background` / `moderation` 原本的作用：

- `background`: OpenAI Images API 的背景控制字段。`gpt-image-2` 不支持 `transparent`，而 `auto` / `opaque` 对大多数普通出图区别不明显，所以节点默认不传。
- `moderation`: 文生图审核强度，通常是 `auto` 或 `low`。它不属于图片编辑接口的核心字段，日常使用默认即可，所以节点主面板不再暴露。

## API 域名

可选域名：

- OpenAI域名：`https://api.openai.com/v1`
- 第三方推荐：
  - HPC4S：`https://api.hpc4s.cn:8317/v1`、`https://api.hpc4s.cn/v1`
  - 易API域名：`https://api.apiyi.com`、`https://api.apiyi.com/v1`

节点底层会兼容带 `/v1` 和不带 `/v1` 的 base url，并把超时拆成连接超时 `30` 秒 + 节点面板里的读取超时秒数，减少长耗时生成时的中断。

鉴权格式：

```text
Authorization: Bearer YOUR_API_KEY
```

项目的前端扩展会把节点中的 `api_key (API密钥)` 替换为真正的密码输入框，默认隐藏内容，并提供“显示/隐藏”切换按钮。API key 的读取规则如下：

- 输入框为空：读取环境变量 `OPENAI_API_KEY`。
- 输入框为其他非空内容：直接使用输入框中的值。
- 输入框需要读取环境变量但 `OPENAI_API_KEY` 未设置或为空：节点会报错并停止请求。

Linux/macOS 可以在启动 ComfyUI 前设置：

```bash
export OPENAI_API_KEY="sk-your-api-key"
```

## 示例工作流

打开 `example_workflow.json`。

里面包含：

- 一个 `gpt-image-2` 示例，使用真实 `size=2048x1152`、`quality=high`、`output_format=jpeg`。
- 中文 Note 节点，说明模型选择、提示词比例控制、真实尺寸控制和图片编辑/mask 用法。

分享工作流前请清空 API Key。

## 常见问题

### gpt-image-2-all 能不能硬控 2K / 4K？

不能。`gpt-image-2-all` 没有 `size` 参数，2K / 4K 只能作为 prompt 描述，无法保证输出像素。当前节点只前置官方推荐比例写法，不额外加入噪音尺寸描述。

### 哪个节点能真实控制分辨率？

如果需要真实 `size`、`quality` 或 mask 局部重绘，用 `Comfyui-Luck gpt-image-2`。`gpt-image-2-all` 只能用 prompt 控制比例，不能承诺像素级锁尺寸。

### 加载旧工作流报 `Value 3 smaller than min of 30`？

这是旧工作流 widget 顺序不匹配导致的：`retry_times=3` 被错读成了 `timeout_seconds=3`。请使用当前 `example_workflow.json`，或重新添加节点。

### 接入 `文本停留编辑器` 后，`gpt-image-2` 报 `Value not in list`？

这是把 `prompt` 转成输入口后，旧 workflow 少了一个 prompt 占位，导致后面的控件整体前移：例如 `mode` 被读成 `gpt-image-2`、`api_base` 被读成 `2K`、`image_size` 被读成 `16:9`。当前节点会在校验阶段放行，并在运行时自动把这些错位参数恢复；新 `example_workflow.json` 也已经补好占位。若界面上仍显示错位，重载当前工作流或重新添加 `Comfyui-Luck gpt-image-2` 节点即可。
