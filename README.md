# Comfyui-Luck gpt-2.0

[简体中文](README_CN.md)

A ComfyUI custom-node package for OpenAI-compatible image generation and prompt understanding. It supports the native OpenAI API as well as compatible proxy services, with API keys and base URLs configurable through environment variables or node widgets.

> [!IMPORTANT]
> Model availability, accepted parameters, output formats, pricing, and latency depend on the selected upstream service. The package registers one Responses API image-tool node and one direct Images API node. Read the node comparison below before choosing one.

## Features

- Official-style `responses`, `images/generations`, and `images/edits` image-generation requests.
- Conversational image generation and editing through the Responses API `image_generation` tool.
- Full `gpt-image-2` size, quality, output-format, multi-image, and mask controls in the Images API node.
- Up to 16 reference images in the full Images API node.
- Text-to-image and reference-image prompt optimizers.
- A workflow pause node for manually editing generated prompts before image generation continues.
- `OPENAI_API_KEY` and `OPENAI_BASE_URL` environment-variable support.
- A real password DOM widget with a show/hide button for API-key fields.
- Runtime status bars with elapsed time and retry-aware estimated progress.
- Image-generation nodes automatically retry HTTP `408`, `429`, and `5xx` responses.

## Registered nodes

| Display name | Internal class | Purpose |
|---|---|---|
| `Comfyui-Luck OpenAI Responses Image` | `ComfyuiLuckGPTResponseNode` | Uses a mainline GPT model such as `gpt-5.6` to call the Responses API `image_generation` tool. Supports reference images, generated-image editing, and multi-turn continuation with `previous_response_id`. |
| `Comfyui-Luck gpt-image-2` | `ComfyuiLuckGPTImage2Node` | Full Images API node with real size, quality, format, up to 16 reference images, and mask editing. |
| `GPT-Image-2 文生图提示词控制器` | `LuckGPTImage2PromptOptimizer` | Two-stage text prompt optimizer: requirement schema extraction followed by final prompt rendering. |
| `图生图提示词控制器` | `LuckReferenceImagePromptOptimizer` | Multimodal prompt optimizer using one required and up to four optional reference images, plus an optional subject image. |
| `文本停留编辑器` | `LuckTextListEditor` | Pauses workflow execution so text can be edited in the browser before downstream nodes continue. |

The removed `ComfyuiLuckGPTImage2VipNode` / `Comfyui-Luck gpt-image-2-vip` node is no longer registered. Workflows that still contain it must replace it with one of the two image nodes above.

## Installation

1. Copy or clone this repository into `ComfyUI/custom_nodes/`.
2. Install the Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

3. Restart ComfyUI.
4. Search for `Comfyui-Luck` in the node menu.

Dependencies declared by the project:

- `numpy`
- `Pillow`
- `requests`
- `torch`

## Authentication and base URL

### API key resolution

The same rule is used by both image nodes and both prompt-optimizer nodes:

1. If the node field `api_key (API密钥)` is non-empty after trimming whitespace, that value is used directly.
2. If the field is empty, the code reads `OPENAI_API_KEY`.
3. If both are empty, execution stops with an error.

The frontend replaces the normal ComfyUI STRING widget with a real `<input type="password">` and adds a `显示/隐藏` (Show/Hide) button.

> [!WARNING]
> Password masking only hides the value on screen. A key entered into a node can still be serialized into the workflow JSON. Clear API-key fields before sharing or publishing workflows.

### Base URL resolution

`DEFAULT_API_BASE_URL` is evaluated when the Python module is imported:

1. Use trimmed `OPENAI_BASE_URL` when it is non-empty.
2. Otherwise use `https://api.hpc4s.cn:8317/v1`.

The node dropdown is built from:

1. The resolved default URL above.
2. `https://api.hpc4s.cn/v1`
3. `https://api.openai.com/v1`
4. `https://api.apiyi.com/v1`

To use another compatible proxy, set `OPENAI_BASE_URL` before starting ComfyUI. Restart ComfyUI after changing either environment variable.

Linux/macOS example:

```bash
export OPENAI_API_KEY="sk-your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
python3 main.py
```

PowerShell example:

```powershell
$env:OPENAI_API_KEY = "sk-your-api-key"
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
python main.py
```

Base URLs ending in `/v1` are used directly. For a base URL without `/v1`, the code inserts `/v1` before the endpoint path.

### Timeouts

HTTP requests use a fixed connection timeout of 60 seconds. The node's `timeout_seconds (超时秒数)` value is used as the read timeout.

## Image node comparison

| Capability | `Comfyui-Luck OpenAI Responses Image` | `Comfyui-Luck gpt-image-2` |
|---|---|---|
| Model type | Mainline GPT model: `gpt-5.6`, `gpt-5.5`, `gpt-5.4`, or `gpt-5` | Direct image model: `gpt-image-2` |
| Endpoint | `/v1/responses` | `/v1/images/generations` or `/v1/images/edits` |
| Text-to-image | Yes | Yes |
| Image editing | Up to 14 reference images or previous response context | Up to 16 images |
| Mask | No | Yes |
| Multi-turn editing | Yes, through `previous_response_id` | No |
| Real size and quality fields | Sent inside the `image_generation` tool | Sent directly to the Images API |
| Output format | `png`, `jpeg`, or `webp` tool options | `png`, `jpeg`, or `webp` request fields |
| Response image field | `output[].result` from an `image_generation_call` | `data[].b64_json` |
| Outputs | `image`, `response`, `response_id` | `image`, `response` |
| Default read timeout | 600 seconds | 600 seconds |

## `Comfyui-Luck OpenAI Responses Image`

This node calls `POST /v1/responses` with a mainline GPT model and the built-in `image_generation` tool. Its internal class and registered node type are both `ComfyuiLuckGPTResponseNode`; the old `ComfyuiLuckGPT20Node` registration and proxy Images API / Chat Completions implementation have been removed.

### Important behavior

- `model (模型)` selects the mainline model that decides when and how to call the image tool. The image model itself is selected by the Responses API.
- `action (操作)`:
  - `auto`: lets the model decide whether to generate or edit.
  - `generate`: forces creation of a new image.
  - `edit`: requires at least one reference image or a `previous_response_id` containing image context.
- `image_size (分辨率)` is a single text field. Enter an explicit size such as `1024x1024` or `1024x3072`; enter `auto` to omit the tool's `size` field.
- Explicit sizes must use `WIDTHxHEIGHT` and satisfy the GPT Image 2 constraints: both edges are multiples of 16, maximum edge 3840, ratio no greater than `3:1`, and total pixels from `655,360` through `8,294,400`.
- `quality`, `output_format`, `output_compression`, and `background` are sent as additional `image_generation` tool options.
- Supports `image_01` through `image_14`.
- Connected images are encoded as Responses API `input_image` content items.
- `previous_response_id (上次响应ID)` continues an earlier Responses conversation for iterative image editing.
- Generated images are decoded from `output[]` items whose type is `image_generation_call`.
- The `response_id` output can be connected to another Responses Image node's `previous_response_id` input.
- `seed (种子)` is a ComfyUI control only and is not sent to the API.

## `Comfyui-Luck gpt-image-2`

This node implements the full Images API request contract used by the project.

### Inputs and request behavior

- `mode (模式)` uses the same `AUTO` / `text2img` / `img2img` behavior described above.
- Text-to-image calls `/v1/images/generations` with JSON.
- Image editing calls `/v1/images/edits` with multipart `image[]` files.
- Supports `image_01` through `image_16`.
- An optional `mask` is sent as `mask.png`; a mask requires at least one input image.
- ComfyUI mask value `1` is treated as the edit area and converted to transparent alpha for the API mask.
- `quality` is omitted when set to `auto`.
- `output_format` and `output_compression` are sent only for `jpeg` or `webp`; `png` leaves both fields out.
- The response parser expects one or more `data[].b64_json` images. A proxy that returns URL-only data is not compatible with this node's current parser.
- `seed` is not sent to the API.

### Preset size table

The code declares the following preset table:

| Aspect ratio | 1K | 2K | 4K |
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

### Custom size validation

When `image_size (分辨率)` is `custom (自定义)`, `custom_size (仅custom填写: 宽x高)` must satisfy all of the following:

- Format: `WIDTHxHEIGHT`, for example `1600x1200`.
- Width and height must be multiples of 16.
- Maximum side must not exceed 3840 pixels.
- Long side / short side must not exceed `3:1`.
- Total pixels must be between `655,360` and `8,294,400`.

Setting `image_size` to `auto (不传size)` or choosing `aspect_ratio=AUTO` for a preset resolves to `auto`, so the request omits `size`.

### Old workflow compatibility

The node includes recovery logic for old workflows whose widget values shifted after converting `prompt` into an input. If a loaded workflow still displays incorrect values, reload it or replace the node with a newly created `Comfyui-Luck gpt-image-2` node.

## Prompt optimizer nodes

Both prompt optimizers call `/v1/chat/completions` with `stream: false` and use the same API-key/base-URL resolution described above.

Available model values:

- `gpt-5.6-terra`
- `gpt-5.6-sol`
- `gpt-5.5`
- `gpt-4o`
- `gpt-4.1-mini`
- `gemini-3.5-flash` (UI default)
- `gemini-2.5-pro`

Availability is determined by the selected upstream service. The `seed` widgets are not sent in API payloads.

### `GPT-Image-2 文生图提示词控制器`

This text-only optimizer performs two API calls:

1. Convert the request into a structured schema.
2. Render the schema into a final image-generation prompt.

Main controls:

- `layout_type`: automatic, image only, mixed text/image poster, e-commerce hero image, or social-media cover.
- `text_policy`: no text, preserve source text, improve source text, or generate text.
- `optimize_strength`: standard or enhanced.
- `aspect_ratio`: target composition ratio.
- `exact_text`: text that should be preserved or used by the selected text policy.

Outputs:

- `optimized_prompt`
- `debug_info`, including model information, normalized schema, renderer input, and final prompt.

### `图生图提示词控制器`

- `reference_image_01` is required.
- `reference_image_02` through `reference_image_05` are optional.
- `subject_image` is optional and is sent before reference images to identify the subject that should be preserved.
- Reference modes include automatic, full reference, style only, composition only, color/lighting only, and layout only.
- Outputs `optimized_prompt` and `reference_summary`.

Connecting images only to this optimizer performs image understanding and prompt generation. To make final image generation actually reference those images, connect the same images to the downstream image node as well.

## `文本停留编辑器`

This node pauses the current execution and opens editable text widgets in the browser.

Recommended chain:

```text
Prompt optimizer optimized_prompt
  -> 文本停留编辑器 text_list
  -> edited_text
  -> image node prompt
```

- `Continue` submits the edited text and resumes the waiting execution.
- `Cancel` interrupts the current execution.
- The wait times out after 3600 seconds and interrupts processing.
- `edited_text` joins non-empty items with newlines and is suitable for a normal prompt input.
- `edited_texts` preserves the list output for batch workflows.

Queue the final `PreviewImage` or `SaveImage` node. While execution is waiting in the editor, use `Continue`; do not press the main queue button again, or upstream prompt generation will run again.

## Frontend extensions

### Password widget

The password extension targets both image nodes and both prompt optimizers. It preserves the original widget name, position, value, and workflow serialization while replacing the visual control with a password input.

After installing or updating the extension, restart ComfyUI and hard-refresh the browser if the API key still appears as a normal text widget.

### Runtime status bar

Both image nodes and both prompt optimizers receive a status bar showing:

- Current phase/message.
- Elapsed time.
- Current attempt or processing stage.
- Estimated progress based on timeout and retry state.
- Success or error state.

The percentage is a local estimate, not progress reported by the upstream model.

## Example workflow

Open `example_workflow.json`. It currently contains three groups:

1. Direct `gpt-image-2` text-to-image generation.
2. Text prompt optimization -> manual text editing -> image generation.
3. Five reference images -> multimodal prompt optimization -> manual text editing -> multi-image generation.

Some demonstration nodes are saved in bypass mode. Enable the group or nodes you want to run, provide images where required, and queue the final preview node.

Before sharing the workflow, clear every API-key widget.

## Troubleshooting

### `API Key 为空，且环境变量 OPENAI_API_KEY 未设置`

Enter a key in the node or set `OPENAI_API_KEY` before starting ComfyUI.

### A changed `OPENAI_BASE_URL` is not visible

The default is read when the Python module is imported. Restart ComfyUI after changing the variable.

### Responses API returned text but no image

`Comfyui-Luck OpenAI Responses Image` requires an `image_generation_call` containing a base64 `result`. Make the prompt explicitly request an image, verify that the selected mainline model supports the image-generation tool, and check that the configured Base URL implements `POST /v1/responses`.

### An old workflow contains `ComfyuiLuckGPT20Node` or `Comfyui-Luck gpt-2.0 all`

The old internal node type is no longer registered. Remove the missing old node and add a new `Comfyui-Luck OpenAI Responses Image` node.

### A Responses Image workflow still shows separate size, aspect-ratio, or custom-size widgets

The Responses node now uses one explicit `image_size` text field. Remove the old node instance and add a new `Comfyui-Luck OpenAI Responses Image` node so legacy positional widget values are not shifted into the remaining controls.

### `mask 只能和 image_01 一起用于图片编辑`

Connect at least one image when using a mask. The first connected image is the base image for the mask edit.

### Timeout, `408`, `429`, or `5xx`

Increase the read timeout for slow generation. The nodes retry retryable HTTP statuses up to `retry_times`. Connection setup still has a fixed 60-second timeout.

### An old workflow contains `ComfyuiLuckGPTImage2VipNode`

That node has been removed. Replace it with `Comfyui-Luck gpt-image-2` for direct Images API generation, or `Comfyui-Luck OpenAI Responses Image` for conversational image generation.

## License

[Apache License 2.0](LICENSE)
