#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comfyui-Luck image nodes for the OpenAI Responses API and Images API.
By default, base-url and api-key are read from environment variables OPENAI_BASE_URL and OPENAI_API_KEY.
If the environment variables are not set, use the default values or the values entered in the input text box.
"""

import base64
import json
import os
import re
import time
from io import BytesIO

import numpy as np
from PIL import Image
import requests
import torch


DEFAULT_API_BASE_URL = os.environ.get("OPENAI_BASE_URL", "").strip() or "https://api.hpc4s.cn:8317/v1"
API_BASE_URLS = [
    DEFAULT_API_BASE_URL,
    "https://api.hpc4s.cn/v1",
    "https://api.openai.com/v1",
    "https://api.apiyi.com/v1",
]
API_CONNECT_TIMEOUT_SECONDS = 60
APIYI_HTTP_SESSION = requests.Session()
APIYI_HTTP_ADAPTER = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
APIYI_HTTP_SESSION.mount("http://", APIYI_HTTP_ADAPTER)
APIYI_HTTP_SESSION.mount("https://", APIYI_HTTP_ADAPTER)

def resolve_api_key(api_key):
    """Use the node API key, falling back to OPENAI_API_KEY only when empty."""
    key = (api_key or "").strip()
    if not key:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("API Key 为空，且环境变量 OPENAI_API_KEY 未设置")
    return key


def apiyi_timeout(timeout_seconds):
    try:
        read_timeout = int(timeout_seconds)
    except (TypeError, ValueError):
        read_timeout = 300
    return (API_CONNECT_TIMEOUT_SECONDS, max(1, read_timeout))


def apiyi_post(url, timeout_seconds, **kwargs):
    return APIYI_HTTP_SESSION.post(url, timeout=apiyi_timeout(timeout_seconds), **kwargs)


def build_api_url(api_base, path):
    """Build OpenAI-compatible endpoint URLs from bases with or without /v1."""
    base = (api_base or DEFAULT_API_BASE_URL).strip().rstrip("/")
    clean_path = str(path or "").strip().lstrip("/")
    if clean_path.startswith("v1/"):
        clean_path = clean_path[3:]
    if base.endswith("/v1"):
        return f"{base}/{clean_path}"
    return f"{base}/v1/{clean_path}"


def http_status_hint(status_code):
    if status_code == 408:
        return "API 返回 408，上游生成超时"
    if status_code == 429:
        return "API 返回 429，限流或额度不足"
    if status_code >= 500:
        return f"API 返回 {status_code}，网关或后端临时错误"
    return f"API 返回 {status_code}"


GPT_IMAGE2_SIZE_TABLE = {
    "1K": {
        "AUTO": "auto",
        "1:4": "480x1440",
        "4:1": "1440x480",
        "1:8": "480x1440",
        "8:1": "1440x480",
        "1:1": "1024x1024",
        "1:2": "720x1440",
        "2:1": "1440x720",
        "1:3": "480x1440",
        "3:1": "1440x480",
        "2:3": "768x1152",
        "3:2": "1152x768",
        "3:4": "768x1024",
        "4:3": "1024x768",
        "4:5": "768x960",
        "5:4": "960x768",
        "9:16": "720x1280",
        "16:9": "1280x720",
        "9:21": "640x1488",
        "21:9": "1344x576",
    },
    "2K": {
        "AUTO": "auto",
        "1:4": "672x2016",
        "4:1": "2016x672",
        "1:8": "672x2016",
        "8:1": "2016x672",
        "1:1": "2048x2048",
        "1:2": "1024x2048",
        "2:1": "2048x1024",
        "1:3": "672x2016",
        "3:1": "2016x672",
        "2:3": "1440x2160",
        "3:2": "2160x1440",
        "3:4": "1536x2048",
        "4:3": "2048x1536",
        "4:5": "1536x1920",
        "5:4": "1920x1536",
        "9:16": "1152x2048",
        "16:9": "2048x1152",
        "9:21": "960x2240",
        "21:9": "2464x1056",
    },
    "4K": {
        "AUTO": "auto",
        "1:4": "1280x3840",
        "4:1": "3840x1280",
        "1:8": "1280x3840",
        "8:1": "3840x1280",
        "1:1": "2880x2880",
        "1:2": "1920x3840",
        "2:1": "3840x1920",
        "1:3": "1280x3840",
        "3:1": "3840x1280",
        "2:3": "2304x3456",
        "3:2": "3456x2304",
        "3:4": "2448x3264",
        "4:3": "3264x2448",
        "4:5": "2304x2880",
        "5:4": "2880x2304",
        "9:16": "2160x3840",
        "16:9": "3840x2160",
        "9:21": "1648x3840",
        "21:9": "3808x1632",
    },
}


def tensor_to_png_bytes(tensor):
    """ComfyUI IMAGE tensor -> PNG bytes."""
    if tensor is None:
        raise ValueError("输入图像为空")

    single = tensor[0:1] if len(tensor.shape) == 4 else tensor.unsqueeze(0)
    arr = (single[0].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def tensor_to_data_url(tensor):
    """ComfyUI IMAGE tensor -> PNG data URL."""
    return "data:image/png;base64," + base64.b64encode(tensor_to_png_bytes(tensor)).decode("utf-8")


def mask_to_png_bytes(mask):
    """ComfyUI MASK -> RGBA PNG mask for OpenAI Images edit.

    ComfyUI mask value 1 means edit area. OpenAI-style image masks use
    transparent pixels as edit area, so alpha is inverted.
    """
    if mask is None:
        return None

    if len(mask.shape) == 3:
        mask_np = mask[0].cpu().numpy()
    else:
        mask_np = mask.cpu().numpy()

    alpha = ((1.0 - mask_np) * 255).clip(0, 255).astype(np.uint8)
    height, width = alpha.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, :3] = 255
    rgba[:, :, 3] = alpha

    buf = BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def image_bytes_to_tensor(image_bytes):
    """Image bytes -> ComfyUI tensor (1,H,W,3)."""
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0).float()


def b64_json_to_tensor(b64_json):
    """Decode API b64_json. APIYi may include a data URL prefix."""
    value = (b64_json or "").strip()
    if not value:
        raise ValueError("b64_json 为空")

    if "," in value and value.lower().startswith("data:"):
        value = value.split(",", 1)[1]

    return image_bytes_to_tensor(base64.b64decode(value))


def _validate_gpt_image2_size(size_value):
    if size_value == "auto":
        return size_value

    if not re.fullmatch(r"\d{3,4}x\d{3,4}", size_value):
        raise ValueError("size 必须类似 1600x1200，且宽高都是数字")

    width, height = [int(v) for v in size_value.split("x")]
    max_side = max(width, height)
    min_side = min(width, height)
    total_pixels = width * height

    if width % 16 != 0 or height % 16 != 0:
        raise ValueError("size 的宽和高都必须是 16 的倍数")
    if max_side > 3840:
        raise ValueError("size 最大边不能超过 3840px")
    if max_side / min_side > 3:
        raise ValueError("size 长边/短边不能超过 3:1，因此 3:1 和 1:3 可以，超过不行")
    if total_pixels < 655360 or total_pixels > 8294400:
        raise ValueError("size 总像素需在 655,360 到 8,294,400 之间")

    return f"{width}x{height}"


def _extract_aspect_ratio(value):
    text = str(value or "")
    if text.upper().startswith("AUTO"):
        return "AUTO"
    match = re.search(
        r"(?:21:9|9:21|16:9|9:16|4:5|5:4|4:3|3:4|3:2|2:3|3:1|1:3|2:1|1:2|1:8|8:1|1:4|4:1|1:1)",
        text,
    )
    return match.group(0) if match else "16:9"


def normalize_size(image_size, aspect_ratio="16:9", custom_size=""):
    option = (image_size or "2K").strip().replace("×", "x")
    option_lower = option.lower()

    if option_lower.startswith("auto"):
        return "auto"

    if option_lower.startswith("custom"):
        custom = (custom_size or "").strip().lower().replace("×", "x")
        if not custom:
            raise ValueError("选择 custom 时，custom_size 必须填写，例如 3072x1024 或 1024x3072")
        return _validate_gpt_image2_size(custom)

    match = re.match(r"(\d{3,4}x\d{3,4})", option_lower)
    if match:
        return _validate_gpt_image2_size(match.group(1))

    tier = None
    if "1k" in option_lower:
        tier = "1K"
    elif "2k" in option_lower:
        tier = "2K"
    elif "4k" in option_lower:
        tier = "4K"

    ratio = _extract_aspect_ratio(aspect_ratio)
    if tier and ratio in GPT_IMAGE2_SIZE_TABLE[tier]:
        return _validate_gpt_image2_size(GPT_IMAGE2_SIZE_TABLE[tier][ratio])

    raise ValueError(f"无法识别尺寸组合: image_size={image_size}, aspect_ratio={aspect_ratio}")


def is_retryable_http_status(status_code):
    return status_code in (408, 429) or status_code >= 500


def safe_choice(value, choices, default):
    return value if value in choices else default


def safe_int(value, default, min_value=None, max_value=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default

    if min_value is not None:
        number = max(min_value, number)
    if max_value is not None:
        number = min(max_value, number)
    return number


def normalize_prompt_text(value):
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def emit_runtime_status(
    node_id,
    status,
    message="",
    elapsed_seconds=0.0,
    attempt=0,
    retry_times=0,
    timeout_seconds=0,
):
    """Send runtime status to the ComfyUI frontend extension."""
    if node_id in (None, ""):
        return
    try:
        from server import PromptServer

        if PromptServer.instance is None:
            return

        PromptServer.instance.send_sync(
            "comfyui_luck_gpt_response_status",
            {
                "node_id": str(node_id),
                "status": status,
                "message": message,
                "elapsed_seconds": float(elapsed_seconds),
                "attempt": int(attempt),
                "retry_times": int(retry_times),
                "timeout_seconds": int(timeout_seconds),
                "timestamp": time.time(),
            },
        )
    except Exception:
        pass


class ComfyuiLuckGPTResponseNode:
    """Generate and edit images through the OpenAI Responses API image tool."""

    MODELS = ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6", "gpt-5.5", "gpt-5.4", "gpt-5"]
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key (API密钥)": ("STRING", {"default": "", "multiline": False}),
                "prompt (提示词)": ("STRING", {"default": "", "multiline": True}),
                "model (模型)": (cls.MODELS, {"default": "gpt-5.6"}),
                "api_base (接口域名)": (API_BASE_URLS, {"default": DEFAULT_API_BASE_URL}),
                "action (操作)": (["auto", "generate", "edit"], {"default": "auto"}),
                "image_size (分辨率)": (
                    "STRING",
                    {
                        "default": "1024x1024",
                        "multiline": False,
                        "tooltip": "填写宽x高，例如 1024x1024；填写 auto 时不发送 size",
                    },
                ),
                "quality (画质)": (["auto", "low", "medium", "high"], {"default": "auto"}),
                "output_format (输出格式)": (["png", "jpeg", "webp"], {"default": "png"}),
                "output_compression (压缩率)": ("INT", {"default": 85, "min": 0, "max": 100}),
                "background (背景)": (["auto", "opaque"], {"default": "auto"}),
                "seed (种子)": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 2147483647,
                        "control_after_generate": True,
                    },
                ),
                "timeout_seconds (超时秒数)": ("INT", {"default": 600, "min": 60, "max": 1800}),
                "retry_times (重试次数)": ("INT", {"default": 3, "min": 1, "max": 10}),
            },
            "optional": {
                "previous_response_id (上次响应ID)": (
                    "STRING",
                    {"default": "", "multiline": False, "forceInput": True},
                ),
                **{f"image_{i:02d}": ("IMAGE",) for i in range(1, 15)},
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "response", "response_id")
    FUNCTION = "generate"
    CATEGORY = "Comfyui-Luck/openai-responses"

    def _collect_images(self, kwargs):
        images = []
        for i in range(1, 15):
            tensor = kwargs.get(f"image_{i:02d}")
            if tensor is not None:
                images.append(tensor_to_data_url(tensor))
        return images

    def _build_input(self, prompt, image_data_urls):
        if not image_data_urls:
            return prompt

        content = [{"type": "input_text", "text": prompt}]
        content.extend(
            {"type": "input_image", "image_url": image_data_url}
            for image_data_url in image_data_urls
        )
        return [{"role": "user", "content": content}]

    def _build_image_tool(self, action, size, quality, output_format, output_compression, background):
        tool = {
            "type": "image_generation",
            "action": action,
        }
        if size != "auto":
            tool["size"] = size
        if quality != "auto":
            tool["quality"] = quality
        if output_format != "png":
            tool["output_format"] = output_format
            tool["output_compression"] = output_compression
        if background != "auto":
            tool["background"] = background
        return tool

    def _request_responses(self, api_base, headers, payload, timeout_seconds):
        return apiyi_post(
            build_api_url(api_base, "responses"),
            timeout_seconds,
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )

    def _extract_output_text(self, data):
        texts = []
        for item in data.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") in ("output_text", "refusal") and content.get("text"):
                    texts.append(str(content["text"]))
        return "\n".join(texts)

    def _parse_response_images(self, data):
        tensors = []
        calls = []
        for item in data.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "image_generation_call":
                continue

            result = item.get("result")
            calls.append(
                {
                    "id": item.get("id"),
                    "status": item.get("status"),
                    "revised_prompt": item.get("revised_prompt"),
                }
            )
            if result:
                tensors.append(b64_json_to_tensor(result))

        if not tensors:
            output_text = self._extract_output_text(data)
            detail = output_text or json.dumps(data, ensure_ascii=False)[:2000]
            raise RuntimeError(f"Responses API 未返回 image_generation_call 图片结果: {detail}")

        expected_shape = tensors[0].shape[1:]
        if any(tensor.shape[1:] != expected_shape for tensor in tensors[1:]):
            raise RuntimeError("Responses API 返回了不同尺寸的多张图片，无法合并为 ComfyUI IMAGE 批次")

        return torch.cat(tensors, dim=0), calls, self._extract_output_text(data)

    def generate(self, **kwargs):
        api_key = kwargs.get("api_key (API密钥)", "")
        prompt = normalize_prompt_text(kwargs.get("prompt (提示词)", ""))
        model = kwargs.get("model (模型)", "gpt-5.6")
        api_base = kwargs.get("api_base (接口域名)", DEFAULT_API_BASE_URL).rstrip("/")
        action = safe_choice(kwargs.get("action (操作)", "auto"), ["auto", "generate", "edit"], "auto")
        image_size = str(kwargs.get("image_size (分辨率)", "1024x1024") or "").strip().lower().replace("×", "x")
        quality = safe_choice(kwargs.get("quality (画质)", "auto"), ["auto", "low", "medium", "high"], "auto")
        output_format = safe_choice(kwargs.get("output_format (输出格式)", "png"), ["png", "jpeg", "webp"], "png")
        output_compression = safe_int(kwargs.get("output_compression (压缩率)", 85), 85, 0, 100)
        background = safe_choice(kwargs.get("background (背景)", "auto"), ["auto", "opaque"], "auto")
        previous_response_id = str(kwargs.get("previous_response_id (上次响应ID)", "") or "").strip()
        seed = safe_int(kwargs.get("seed (种子)", 0), 0, 0, 2147483647)
        timeout_seconds = safe_int(kwargs.get("timeout_seconds (超时秒数)", 600), 600, 60, 1800)
        retry_times = safe_int(kwargs.get("retry_times (重试次数)", 3), 3, 1, 10)
        unique_id = kwargs.get("unique_id")
        start_ts = time.time()

        if not prompt:
            raise ValueError("prompt 不能为空")

        try:
            api_key = resolve_api_key(api_key)
        except ValueError as exc:
            emit_runtime_status(unique_id, "error", str(exc), 0.0, 0, retry_times, timeout_seconds)
            raise

        if not image_size:
            raise ValueError("image_size 不能为空，请填写例如 1024x1024 或 auto")
        effective_size = _validate_gpt_image2_size(image_size)
        image_data_urls = self._collect_images(kwargs)
        if action == "edit" and not image_data_urls and not previous_response_id:
            raise ValueError("action=edit 时必须连接参考图或填写 previous_response_id")

        image_tool = self._build_image_tool(
            action,
            effective_size,
            quality,
            output_format,
            output_compression,
            background,
        )
        payload = {
            "model": model,
            "input": self._build_input(prompt, image_data_urls),
            "tools": [image_tool],
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        headers = {"Authorization": f"Bearer {api_key}"}
        last_error = None

        print(f"[Comfyui-Luck Responses Image] 使用 seed: {seed} (not sent to API)")
        print(
            f"[Comfyui-Luck Responses Image] model={model}, api_base={api_base}, "
            f"action={action}, input_images={len(image_data_urls)}, tool={image_tool}, "
            f"timeout={timeout_seconds}s, retry={retry_times}"
        )
        emit_runtime_status(unique_id, "running", "开始生成", 0.0, 0, retry_times, timeout_seconds)

        for attempt in range(1, retry_times + 1):
            try:
                print(f"[Comfyui-Luck Responses Image] 请求中... (尝试 {attempt}/{retry_times})")
                emit_runtime_status(
                    unique_id,
                    "running",
                    f"Responses 图像生成请求中 ({attempt}/{retry_times})",
                    time.time() - start_ts,
                    attempt,
                    retry_times,
                    timeout_seconds,
                )
                response = self._request_responses(api_base, headers, payload, timeout_seconds)

                if response.status_code != 200:
                    hint = http_status_hint(response.status_code)
                    last_error = f"{hint}: {response.text}"
                    print(f"[Comfyui-Luck Responses Image] {last_error[:1000]}")
                    if is_retryable_http_status(response.status_code) and attempt < retry_times:
                        emit_runtime_status(
                            unique_id,
                            "running",
                            f"{hint}，重试中 ({attempt}/{retry_times})",
                            time.time() - start_ts,
                            attempt,
                            retry_times,
                            timeout_seconds,
                        )
                        time.sleep(min(2 ** (attempt - 1), 8))
                        continue
                    raise RuntimeError(last_error)

                try:
                    data = response.json()
                except ValueError as exc:
                    raise RuntimeError(f"Responses API 返回了无效 JSON: {response.text[:1000]}") from exc

                emit_runtime_status(
                    unique_id,
                    "running",
                    "解析 image_generation_call",
                    time.time() - start_ts,
                    attempt,
                    retry_times,
                    timeout_seconds,
                )
                image_tensor, image_calls, output_text = self._parse_response_images(data)
                elapsed = time.time() - start_ts
                response_id = str(data.get("id") or "")
                response_info = {
                    "status": "success",
                    "model": model,
                    "endpoint": "responses",
                    "api_base": api_base,
                    "response_id": response_id,
                    "previous_response_id": previous_response_id,
                    "action": action,
                    "image_size": image_size,
                    "resolved_size": effective_size,
                    "image_tool": image_tool,
                    "input_images": len(image_data_urls),
                    "output_images": int(image_tensor.shape[0]),
                    "image_generation_calls": image_calls,
                    "output_text": output_text,
                    "usage": data.get("usage"),
                    "request_id": (getattr(response, "headers", None) or {}).get("x-request-id"),
                    "seed": seed,
                    "seed_note": "seed is a ComfyUI control only and is not sent to the Responses API",
                    "elapsed_seconds": round(elapsed, 2),
                }

                emit_runtime_status(
                    unique_id,
                    "success",
                    f"生成成功 (耗时 {elapsed:.1f}s)",
                    elapsed,
                    attempt,
                    retry_times,
                    timeout_seconds,
                )
                print(f"[Comfyui-Luck Responses Image] 生成成功，耗时 {elapsed:.1f}s")
                return (
                    image_tensor,
                    json.dumps(response_info, ensure_ascii=False, indent=2),
                    response_id,
                )

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if isinstance(exc, requests.exceptions.Timeout):
                    last_error = f"本地等待超时或读取超时: {exc}"
                else:
                    last_error = f"网络连接异常: {exc}"
                print(f"[Comfyui-Luck Responses Image] {last_error}")
                if attempt < retry_times:
                    emit_runtime_status(
                        unique_id,
                        "running",
                        f"{last_error.split(':', 1)[0]}，重试中 ({attempt}/{retry_times})",
                        time.time() - start_ts,
                        attempt,
                        retry_times,
                        timeout_seconds,
                    )
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                print(f"[Comfyui-Luck Responses Image] 执行失败: {last_error[:1000]}")
                emit_runtime_status(
                    unique_id,
                    "error",
                    last_error,
                    time.time() - start_ts,
                    attempt,
                    retry_times,
                    timeout_seconds,
                )
                raise

        elapsed = time.time() - start_ts
        emit_runtime_status(
            unique_id,
            "error",
            f"连续 {retry_times} 次失败：{last_error}",
            elapsed,
            retry_times,
            retry_times,
            timeout_seconds,
        )
        print(f"[Comfyui-Luck Responses Image] 连续 {retry_times} 次失败，最后错误: {last_error}")
        raise RuntimeError(f"Comfyui-Luck Responses Image 连续 {retry_times} 次失败，最后错误: {last_error}")


class ComfyuiLuckGPTImage2Node:
    """Official gpt-image-2 node with real size, quality, format, and mask controls."""

    MODELS = ["gpt-image-2"]
    IMAGE_SIZES = [
        "auto (不传size)",
        "1K",
        "2K",
        "4K",
        "custom (自定义)",
    ]
    ASPECT_RATIOS = [
        "AUTO",
        "1:4",
        "4:1",
        "1:8",
        "8:1",
        "1:1",
        "1:2",
        "2:1",
        "1:3",
        "3:1",
        "2:3",
        "3:2",
        "3:4",
        "4:3",
        "4:5",
        "5:4",
        "9:16",
        "16:9",
        "9:21",
        "21:9",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key (API密钥)": ("STRING", {"default": "", "multiline": False}),
                "prompt (提示词)": ("STRING", {"default": "", "multiline": True}),
                "mode (模式)": (["AUTO", "text2img", "img2img"], {"default": "AUTO"}),
                "model (模型)": (cls.MODELS, {"default": "gpt-image-2"}),
                "api_base (接口域名)": (API_BASE_URLS, {"default": DEFAULT_API_BASE_URL}),
                "image_size (分辨率)": (cls.IMAGE_SIZES, {"default": "2K"}),
                "aspect_ratio (宽高比)": (cls.ASPECT_RATIOS, {"default": "16:9"}),
                "custom_size (仅custom填写: 宽x高)": ("STRING", {"default": "1600x1200", "multiline": False}),
                "quality (画质)": (["auto", "low", "medium", "high"], {"default": "auto"}),
                "output_format (输出格式)": (["png", "jpeg", "webp"], {"default": "png"}),
                "output_compression (压缩率)": ("INT", {"default": 85, "min": 0, "max": 100}),
                "seed (种子)": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 2147483647,
                        "control_after_generate": True,
                    },
                ),
                "timeout_seconds (超时秒数)": ("INT", {"default": 600, "min": 60, "max": 1800}),
                "retry_times (重试次数)": ("INT", {"default": 3, "min": 1, "max": 10}),
            },
            "optional": {
                **{f"image_{i:02d}": ("IMAGE",) for i in range(1, 17)},
                "mask": ("MASK",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, input_types):
        return True

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "response")
    FUNCTION = "generate"
    CATEGORY = "Comfyui-Luck/gpt-image-2"

    def _collect_images(self, kwargs):
        image_payloads = []
        for i in range(1, 17):
            tensor = kwargs.get(f"image_{i:02d}")
            if tensor is None:
                continue
            image_payloads.append((f"image_{i:02d}.png", tensor_to_png_bytes(tensor)))
        return image_payloads

    def _payload_fields(self, model, prompt, size, quality, output_format, output_compression):
        fields = {
            "model": model,
            "prompt": prompt,
        }
        if size != "auto":
            fields["size"] = size
        if quality != "auto":
            fields["quality"] = quality
        if output_format != "png":
            fields["output_format"] = output_format
            fields["output_compression"] = output_compression
        return fields

    def _request_text2img(self, api_base, headers, fields, timeout_seconds):
        return apiyi_post(
            build_api_url(api_base, "images/generations"),
            timeout_seconds,
            headers={**headers, "Content-Type": "application/json"},
            json=fields,
        )

    def _request_img2img(self, api_base, headers, fields, image_payloads, mask_bytes, timeout_seconds):
        files = [
            ("image[]", (filename, BytesIO(image_bytes), "image/png"))
            for filename, image_bytes in image_payloads
        ]
        if mask_bytes is not None:
            files.append(("mask", ("mask.png", BytesIO(mask_bytes), "image/png")))

        data = {key: str(value) for key, value in fields.items()}
        return apiyi_post(
            build_api_url(api_base, "images/edits"),
            timeout_seconds,
            headers=headers,
            data=data,
            files=files,
        )

    def _parse_response_images(self, data):
        items = data.get("data")
        if not items:
            raise RuntimeError(f"API 未返回图片数据: {data}")
        if not isinstance(items, list):
            items = [items]

        tensors = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("b64_json"):
                tensors.append(b64_json_to_tensor(item["b64_json"]))

        if not tensors:
            raise RuntimeError(f"未能解析 gpt-image-2 响应图片: {data}")

        return torch.cat(tensors, dim=0)

    def generate(self, **kwargs):
        api_key = kwargs.get("api_key (API密钥)", "")
        prompt = kwargs.get("prompt (提示词)", "")
        mode = kwargs.get("mode (模式)", "AUTO")
        model = kwargs.get("model (模型)", "gpt-image-2")
        api_base = kwargs.get("api_base (接口域名)", DEFAULT_API_BASE_URL).rstrip("/")
        image_size = kwargs.get(
            "image_size (分辨率)",
            kwargs.get("size_ratio (尺寸/比例)", kwargs.get("size (尺寸)", "2K")),
        )
        aspect_ratio = kwargs.get("aspect_ratio (宽高比)", "16:9")
        custom_size = kwargs.get(
            "custom_size (仅custom填写: 宽x高)",
            kwargs.get(
                "custom_size (custom时: 宽x高, 例3072x1024)",
                kwargs.get("custom_size (自定义尺寸)", ""),
            ),
        )
        if (
            mode not in ("AUTO", "text2img", "img2img")
            and isinstance(model, str)
            and model.startswith("http")
        ):
            # Old workflows can shift widget values after converting prompt to
            # an input. Recover the intended gpt-image-2 settings instead of
            # sending model=https://... or size=16:9 to the API.
            shifted_api_base = model
            shifted_image_size = api_base
            shifted_aspect_ratio = image_size
            shifted_custom_size = aspect_ratio
            shifted_quality = custom_size
            shifted_output_format = kwargs.get("quality (画质)", "png")
            shifted_output_compression = kwargs.get("output_format (输出格式)", 85)

            mode = "AUTO"
            model = "gpt-image-2"
            api_base = shifted_api_base.rstrip("/")
            image_size = shifted_image_size
            aspect_ratio = shifted_aspect_ratio
            custom_size = shifted_custom_size
            kwargs["quality (画质)"] = shifted_quality
            kwargs["output_format (输出格式)"] = shifted_output_format
            kwargs["output_compression (压缩率)"] = shifted_output_compression
            kwargs["timeout_seconds (超时秒数)"] = 600

        quality = safe_choice(kwargs.get("quality (画质)", "auto"), ["auto", "low", "medium", "high"], "auto")
        output_format = safe_choice(kwargs.get("output_format (输出格式)", "png"), ["png", "jpeg", "webp"], "png")
        output_compression = safe_int(kwargs.get("output_compression (压缩率)", 85), 85, 0, 100)
        seed = safe_int(kwargs.get("seed (种子)", 0), 0, 0, 2147483647)
        timeout_seconds = safe_int(kwargs.get("timeout_seconds (超时秒数)", 600), 600, 60, 1800)
        retry_times = safe_int(kwargs.get("retry_times (重试次数)", 3), 3, 1, 10)
        unique_id = kwargs.get("unique_id")
        start_ts = time.time()

        try:
            api_key = resolve_api_key(api_key)
        except ValueError as exc:
            emit_runtime_status(unique_id, "error", str(exc), 0.0, 0, retry_times, timeout_seconds)
            raise

        clean_prompt = normalize_prompt_text(prompt)
        if not clean_prompt:
            raise ValueError("prompt 不能为空")

        effective_size = normalize_size(image_size, aspect_ratio, custom_size)
        image_payloads = self._collect_images(kwargs)
        mask_bytes = mask_to_png_bytes(kwargs.get("mask"))

        if mode == "AUTO":
            actual_mode = "img2img" if image_payloads else "text2img"
        else:
            actual_mode = mode

        if actual_mode == "img2img" and not image_payloads:
            emit_runtime_status(unique_id, "error", "img2img 模式需要至少一张参考图", 0.0, 0, retry_times, timeout_seconds)
            raise ValueError("img2img 模式需要至少一张参考图")
        if mask_bytes is not None and not image_payloads:
            raise ValueError("mask 只能和 image_01 一起用于图片编辑")

        headers = {"Authorization": f"Bearer {api_key}"}
        fields = self._payload_fields(
            model,
            clean_prompt,
            effective_size,
            quality,
            output_format,
            output_compression,
        )

        print(f"[Comfyui-Luck gpt-image-2] 使用 seed: {seed} (not sent to API)")
        print(f"[Comfyui-Luck gpt-image-2] mode={actual_mode}, api_base={api_base}, image_size={image_size}, aspect_ratio={aspect_ratio}, quality={quality}, timeout={timeout_seconds}s, retry={retry_times}, fields={fields}")
        emit_runtime_status(unique_id, "running", "开始生成", 0.0, 0, retry_times, timeout_seconds)

        last_error = None
        for attempt in range(1, retry_times + 1):
            try:
                print(f"[Comfyui-Luck gpt-image-2] 请求中... (尝试 {attempt}/{retry_times})")
                emit_runtime_status(
                    unique_id,
                    "running",
                    f"{'图片编辑' if actual_mode == 'img2img' else '文生图'}请求中 ({attempt}/{retry_times})",
                    time.time() - start_ts,
                    attempt,
                    retry_times,
                    timeout_seconds,
                )

                if actual_mode == "img2img":
                    response = self._request_img2img(
                        api_base,
                        headers,
                        fields,
                        image_payloads,
                        mask_bytes,
                        timeout_seconds,
                    )
                else:
                    response = self._request_text2img(api_base, headers, fields, timeout_seconds)

                if response.status_code != 200:
                    hint = http_status_hint(response.status_code)
                    last_error = f"{hint}: {response.text}"
                    print(f"[Comfyui-Luck gpt-image-2] {last_error[:1000]}")
                    if is_retryable_http_status(response.status_code) and attempt < retry_times:
                        emit_runtime_status(
                            unique_id,
                            "running",
                            f"{hint}，重试中 ({attempt}/{retry_times})",
                            time.time() - start_ts,
                            attempt,
                            retry_times,
                            timeout_seconds,
                        )
                        time.sleep(min(2 ** (attempt - 1), 8))
                        continue
                    raise RuntimeError(last_error)

                data = response.json()
                emit_runtime_status(
                    unique_id,
                    "running",
                    "解析图片",
                    time.time() - start_ts,
                    attempt,
                    retry_times,
                    timeout_seconds,
                )
                image_tensor = self._parse_response_images(data)
                elapsed = time.time() - start_ts
                response_info = {
                    "status": "success",
                    "model": model,
                    "mode": actual_mode,
                    "api_base": api_base,
                    "image_size": image_size,
                    "aspect_ratio": aspect_ratio,
                    "resolved_size": effective_size,
                    "request_fields": fields,
                    "input_images": len(image_payloads),
                    "mask": mask_bytes is not None,
                    "output_images": int(image_tensor.shape[0]),
                    "usage": data.get("usage"),
                    "seed": seed,
                    "seed_note": "seed is a ComfyUI control only and is not sent to gpt-image-2",
                    "elapsed_seconds": round(elapsed, 2),
                }
                emit_runtime_status(
                    unique_id,
                    "success",
                    f"生成成功 (耗时 {elapsed:.1f}s)",
                    elapsed,
                    attempt,
                    retry_times,
                    timeout_seconds,
                )
                print(f"[Comfyui-Luck gpt-image-2] 生成成功，耗时 {elapsed:.1f}s")
                return (image_tensor, json.dumps(response_info, ensure_ascii=False, indent=2))

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if isinstance(exc, requests.exceptions.Timeout):
                    last_error = f"本地等待超时或读取超时: {exc}"
                else:
                    last_error = f"网络连接异常: {exc}"
                print(f"[Comfyui-Luck gpt-image-2] {last_error}")
                if attempt < retry_times:
                    emit_runtime_status(
                        unique_id,
                        "running",
                        f"{last_error.split(':', 1)[0]}，重试中 ({attempt}/{retry_times})",
                        time.time() - start_ts,
                        attempt,
                        retry_times,
                        timeout_seconds,
                    )
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                print(f"[Comfyui-Luck gpt-image-2] 执行失败: {last_error[:1000]}")
                emit_runtime_status(
                    unique_id,
                    "error",
                    last_error,
                    time.time() - start_ts,
                    attempt,
                    retry_times,
                    timeout_seconds,
                )
                raise

        elapsed = time.time() - start_ts
        emit_runtime_status(
            unique_id,
            "error",
            f"连续 {retry_times} 次失败：{last_error}",
            elapsed,
            retry_times,
            retry_times,
            timeout_seconds,
        )
        print(f"[Comfyui-Luck gpt-image-2] 连续 {retry_times} 次失败，最后错误: {last_error}")
        raise RuntimeError(f"Comfyui-Luck gpt-image-2 连续 {retry_times} 次失败，最后错误: {last_error}")


NODE_CLASS_MAPPINGS = {
    "ComfyuiLuckGPTResponseNode": ComfyuiLuckGPTResponseNode,
    "ComfyuiLuckGPTImage2Node": ComfyuiLuckGPTImage2Node,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ComfyuiLuckGPTResponseNode": "Comfyui-Luck OpenAI Responses Image",
    "ComfyuiLuckGPTImage2Node": "Comfyui-Luck gpt-image-2",
}
