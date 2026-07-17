# Comfyui-Luck gpt-2.0

[English](README.md)

这是一个面向 OpenAI 兼容接口的 ComfyUI 自定义节点包，用于图像生成、图片编辑、图像理解和提示词优化。项目支持原生 OpenAI API，也支持兼容 OpenAI 协议的第三方代理服务；API Key 和 Base URL 均可通过环境变量或节点控件配置。

> [!IMPORTANT]
> 实际可用模型、支持参数、返回格式、价格和耗时由所选上游服务决定。项目注册了一个 Responses API 图像工具节点和一个直接 Images API 节点。使用前请先阅读下面的节点对比。

## 功能特性

- 按 OpenAI 官方契约调用 `responses`、`images/generations` 和 `images/edits` 出图接口。
- 通过 Responses API 的 `image_generation` 工具实现对话式生图和图片编辑。
- 支持 `gpt-image-2` 的真实尺寸、画质、输出格式、多参考图和 mask 编辑。
- 完整 Images API 节点最多支持 16 张参考图。
- 提供文生图提示词控制器和参考图提示词控制器。
- 提供文本停留编辑器，可在出图前暂停工作流并手动修改提示词。
- 支持 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 环境变量。
- API Key 使用真正的密码 DOM 输入框，并带“显示/隐藏”按钮。
- API 节点带运行状态栏，可显示耗时和结合重试状态估算的进度。
- 对 HTTP `408`、`429` 和 `5xx` 响应进行自动重试。

## 已注册节点

| 显示名称 | 内部类名 | 用途 |
|---|---|---|
| `Comfyui-Luck OpenAI Responses Image` | `ComfyuiLuckGPTResponseNode` | 使用 `gpt-5.6` 等主线 GPT 模型调用 Responses API 的 `image_generation` 工具，支持参考图、生成图编辑和通过 `previous_response_id` 进行多轮续接。 |
| `Comfyui-Luck gpt-image-2` | `ComfyuiLuckGPTImage2Node` | 完整 Images API 节点，支持真实 size、quality、输出格式、最多 16 张参考图和 mask 编辑。 |
| `GPT-Image-2 文生图提示词控制器` | `LuckGPTImage2PromptOptimizer` | 两阶段文本提示词优化：先整理需求 Schema，再渲染最终提示词。 |
| `图生图提示词控制器` | `LuckReferenceImagePromptOptimizer` | 多模态提示词优化器，支持 1 张必填参考图、最多 4 张可选参考图，以及可选主体图。 |
| `文本停留编辑器` | `LuckTextListEditor` | 暂停工作流，在浏览器中编辑文本后再继续执行后续节点。 |

`ComfyuiLuckGPTImage2VipNode` / `Comfyui-Luck gpt-image-2-vip` 已被删除，不再注册。仍包含该节点的旧工作流需要改用上表中的出图节点。

## 安装

1. 将本项目复制或克隆到 `ComfyUI/custom_nodes/`。
2. 安装 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

3. 重启 ComfyUI。
4. 在节点菜单中搜索 `Comfyui-Luck`。

项目声明的依赖：

- `numpy`
- `Pillow`
- `requests`
- `torch`

## 鉴权与 Base URL

### API Key 解析规则

两个出图节点和两个提示词控制器使用同一套规则：

1. 如果节点中的 `api_key (API密钥)` 去除首尾空格后非空，直接使用该值。
2. 如果输入框为空，则读取 `OPENAI_API_KEY`。
3. 如果两者都为空，节点报错并停止执行。

前端扩展会把 ComfyUI 普通 STRING 控件替换为真正的 `<input type="password">`，并增加 `显示/隐藏` 按钮。

> [!WARNING]
> 密码遮罩只负责界面隐藏。直接输入节点的 API Key 仍可能被序列化进工作流 JSON。分享或发布工作流前必须清空所有 API Key 输入框。

### Base URL 解析规则

Python 模块加载时会计算 `DEFAULT_API_BASE_URL`：

1. 如果 `OPENAI_BASE_URL` 去除首尾空格后非空，使用该值。
2. 否则使用 `https://api.hpc4s.cn:8317/v1`。

节点下拉列表由以下地址组成：

1. 上面解析得到的默认地址。
2. `https://api.hpc4s.cn/v1`
3. `https://api.openai.com/v1`
4. `https://api.apiyi.com/v1`

如果需要其他兼容代理地址，请在启动 ComfyUI 前设置 `OPENAI_BASE_URL`。修改环境变量后需要重启 ComfyUI。

Linux/macOS 示例：

```bash
export OPENAI_API_KEY="sk-your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
python3 main.py
```

PowerShell 示例：

```powershell
$env:OPENAI_API_KEY = "sk-your-api-key"
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
python main.py
```

Base URL 如果以 `/v1` 结尾，会直接追加接口路径；如果不带 `/v1`，代码会先补上 `/v1`。

### 超时

HTTP 请求的连接超时固定为 60 秒。节点中的 `timeout_seconds (超时秒数)` 用作读取超时。

## 出图节点对比

| 能力 | `Comfyui-Luck OpenAI Responses Image` | `Comfyui-Luck gpt-image-2` |
|---|---|---|
| 模型类型 | 主线 GPT 模型：`gpt-5.6`、`gpt-5.5`、`gpt-5.4` 或 `gpt-5` | 直接图像模型：`gpt-image-2` |
| 端点 | `/v1/responses` | `/v1/images/generations` 或 `/v1/images/edits` |
| 文生图 | 支持 | 支持 |
| 图片编辑 | 最多 14 张参考图，或使用上一次响应上下文 | 最多 16 张图 |
| Mask | 不支持 | 支持 |
| 多轮编辑 | 支持，通过 `previous_response_id` | 不支持 |
| 真实尺寸和画质 | 作为 `image_generation` 工具参数发送 | 直接发送给 Images API |
| 输出格式 | 工具参数支持 `png`、`jpeg`、`webp` | 请求字段支持 `png`、`jpeg`、`webp` |
| 响应图片字段 | `image_generation_call` 的 `output[].result` | `data[].b64_json` |
| 输出 | `image`、`response`、`response_id` | `image`、`response` |
| 默认读取超时 | 600 秒 | 600 秒 |

## `Comfyui-Luck OpenAI Responses Image`

该节点使用主线 GPT 模型和内置 `image_generation` 工具调用 `POST /v1/responses`。内部类名和注册节点类型均为 `ComfyuiLuckGPTResponseNode`；旧的 `ComfyuiLuckGPT20Node` 注册以及代理 Images API / Chat Completions 出图实现已经删除。

### 主要行为

- `model (模型)` 选择负责调用图像工具的主线模型，实际图像模型由 Responses API 选择。
- `action (操作)`：
  - `auto`：由模型决定生成新图还是编辑已有图片。
  - `generate`：强制生成新图片。
  - `edit`：必须连接至少一张参考图，或提供包含图片上下文的 `previous_response_id`。
- `image_size (分辨率)` 是单一文本框，直接填写 `1024x1024`、`1024x3072` 等明确尺寸；填写 `auto` 时不发送工具的 `size` 字段。
- 明确尺寸必须使用 `宽x高` 格式，并满足 GPT Image 2 约束：宽高均为 16 的倍数、最大边不超过 3840、长短边比例不超过 `3:1`、总像素在 `655,360` 到 `8,294,400` 之间。
- `quality`、`output_format`、`output_compression` 和 `background` 会作为其他 `image_generation` 工具参数发送。
- 支持 `image_01` 到 `image_14`。
- 连接的参考图会编码为 Responses API 的 `input_image` 内容项。
- `previous_response_id (上次响应ID)` 用于续接之前的 Responses 对话，实现迭代式图片编辑。
- 生成图片从类型为 `image_generation_call` 的 `output[]` 项中解析。
- 输出的 `response_id` 可以连接到下一个 Responses Image 节点的 `previous_response_id` 输入。
- `seed (种子)` 只作为 ComfyUI 控件，不会发送给 API。

## `Comfyui-Luck gpt-image-2`

该节点实现项目中的完整 Images API 请求契约。

### 输入与请求行为

- `mode (模式)` 使用上面相同的 `AUTO` / `text2img` / `img2img` 规则。
- 文生图通过 JSON 调用 `/v1/images/generations`。
- 图片编辑通过 multipart `image[]` 文件调用 `/v1/images/edits`。
- 支持 `image_01` 到 `image_16`。
- 可选 `mask` 会作为 `mask.png` 发送；使用 mask 时必须至少连接一张图片。
- ComfyUI mask 值 `1` 表示编辑区域，发送前会转换为透明 alpha。
- `quality=auto` 时不发送 quality 字段。
- 只有 `jpeg` 或 `webp` 会发送 `output_format` 和 `output_compression`；选择 `png` 时两个字段都不发送。
- 当前响应解析器要求返回一个或多个 `data[].b64_json`。只返回 URL 的代理与该节点当前实现不兼容。
- `seed` 不会发送给 API。

### 预设尺寸表

代码中声明了以下预设：

| 宽高比 | 1K | 2K | 4K |
|---|---:|---:|---:|
| `AUTO` | `auto` | `auto` | `auto` |
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

### 自定义尺寸校验

当 `image_size (分辨率)` 选择 `custom (自定义)` 时，`custom_size (仅custom填写: 宽x高)` 必须同时满足：

- 格式为 `宽x高`，例如 `1600x1200`。
- 宽和高都必须是 16 的倍数。
- 最大边不能超过 3840 像素。
- 长边 / 短边不能超过 `3:1`。
- 总像素必须在 `655,360` 到 `8,294,400` 之间。

`image_size` 选择 `auto (不传size)`，或预设尺寸配合 `aspect_ratio=AUTO` 时，会解析为 `auto`，请求中不发送 size。

### 旧工作流兼容

节点包含旧工作流参数错位恢复逻辑，用于处理把 `prompt` 转成输入口后 widget 值整体前移的情况。如果加载后界面仍显示错误，重新加载工作流，或重新添加一个新的 `Comfyui-Luck gpt-image-2` 节点。

## 提示词控制器

两个提示词控制器都通过 `/v1/chat/completions` 发起 `stream: false` 请求，并使用前面相同的 API Key 和 Base URL 解析规则。

可选模型：

- `gpt-5.6-terra`
- `gpt-5.6-sol`
- `gpt-5.5`
- `gpt-4o`
- `gpt-4.1-mini`
- `gemini-3.5-flash`（界面默认值）
- `gemini-2.5-pro`

具体模型是否可用由上游服务决定。`seed` 控件不会放入 API 请求体。

### `GPT-Image-2 文生图提示词控制器`

这是纯文本两阶段优化器，会发起两次 API 请求：

1. 把用户需求整理成结构化 Schema。
2. 把 Schema 渲染成最终生图提示词。

主要控件：

- `layout_type`：自动判断、纯画面、图文混排海报、电商主图、社媒封面。
- `text_policy`：不加文字、保留原文、优化原文、自动生成。
- `optimize_strength`：标准或增强。
- `aspect_ratio`：目标构图比例。
- `exact_text`：需要保留或交给文字策略使用的准确文本。

输出：

- `optimized_prompt`
- `debug_info`，包含模型信息、规范化 Schema、渲染器输入和最终提示词。

### `图生图提示词控制器`

- `reference_image_01` 必填。
- `reference_image_02` 到 `reference_image_05` 可选。
- `subject_image` 可选，并会先于参考图发送，用来说明需要锁定的主体。
- 参考模式包括：自动判断、综合参考、只参考风格、只参考构图、只参考色彩光影、只参考版式。
- 输出 `optimized_prompt` 和 `reference_summary`。

只把图片连接到该控制器时，仅执行图像理解和提示词生成。如果最终出图也需要真实参考这些图片，应把同一批图片同时连接到后面的出图节点。

## `文本停留编辑器`

该节点会暂停当前执行，并在浏览器中创建可编辑文本控件。

推荐连接方式：

```text
提示词控制器 optimized_prompt
  -> 文本停留编辑器 text_list
  -> edited_text
  -> 出图节点 prompt
```

- 点击 `Continue` 提交修改后的文本并继续当前等待中的执行。
- 点击 `Cancel` 中断当前执行。
- 等待超过 3600 秒会超时并中断处理。
- `edited_text` 会用换行连接非空项目，适合连接普通 prompt 输入。
- `edited_texts` 保留列表输出，适合批量工作流。

运行时应对最终 `PreviewImage` 或 `SaveImage` 节点发起队列。流程停在编辑器时请点击 `Continue`，不要再次点击主运行按钮，否则会重新执行上游提示词生成。

## 前端扩展

### API Key 密码控件

密码扩展作用于两个出图节点和两个提示词控制器。它在保留原 widget 名称、位置、值和工作流序列化的同时，把显示控件替换为密码输入框。

安装或更新扩展后，如果 API Key 仍显示为普通文本框，请重启 ComfyUI 并强制刷新浏览器。

### 运行状态栏

两个出图节点和两个提示词控制器会显示状态栏，包括：

- 当前阶段或消息。
- 已用时间。
- 当前重试次数。
- 根据超时和重试状态估算的进度。
- 成功或错误状态。

百分比是本地估算值，不是上游模型返回的真实生成进度。

## 示例工作流

打开 `example_workflow.json`，当前包含三个分组：

1. 直接使用 `gpt-image-2` 文生图。
2. 文本提示词优化 -> 手动编辑 -> 出图。
3. 5 张参考图 -> 多模态提示词优化 -> 手动编辑 -> 多图参考出图。

部分演示节点以 bypass 模式保存。请启用需要运行的分组或节点，为必填图片输入提供图像，然后对最终预览节点发起队列。

分享工作流前请清空所有 API Key 输入框。

## 常见问题

### `API Key 为空，且环境变量 OPENAI_API_KEY 未设置`

在节点中输入 API Key，或在启动 ComfyUI 前设置 `OPENAI_API_KEY`。

### 修改 `OPENAI_BASE_URL` 后没有生效

默认值在 Python 模块加载时读取。修改后必须重启 ComfyUI。

### Responses API 返回了文字但没有图片

`Comfyui-Luck OpenAI Responses Image` 要求响应中存在包含 Base64 `result` 的 `image_generation_call`。请在提示词中明确要求生成图片，确认所选主线模型支持图像生成工具，并检查 Base URL 是否实现了 `POST /v1/responses`。

### 旧工作流包含 `ComfyuiLuckGPT20Node` 或 `Comfyui-Luck gpt-2.0 all`

旧内部节点类型已经不再注册。请删除工作流中缺失的旧节点，并重新添加 `Comfyui-Luck OpenAI Responses Image`。

### Responses Image 旧工作流仍显示独立的分辨率、宽高比或自定义尺寸控件

Responses 节点现在只使用一个明确的 `image_size` 文本框。请删除旧节点实例并重新添加 `Comfyui-Luck OpenAI Responses Image`，避免旧工作流的按位置保存值错位到后续控件。

### `mask 只能和 image_01 一起用于图片编辑`

使用 mask 时至少连接一张图片。第一张连接的图片是 mask 编辑的基础图。

### 超时、`408`、`429` 或 `5xx`

慢速生成可以提高读取超时。节点会按照 `retry_times` 重试可重试的 HTTP 状态；连接建立超时仍固定为 60 秒。

### 旧工作流包含 `ComfyuiLuckGPTImage2VipNode`

该节点已经删除。直接调用 Images API 时请替换为 `Comfyui-Luck gpt-image-2`；需要对话式生图时请使用 `Comfyui-Luck OpenAI Responses Image`。

## 许可证

[Apache License 2.0](LICENSE)
