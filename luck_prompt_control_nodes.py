#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt-control helper nodes for Comfyui-Luck gpt-2.0.

These nodes are adapted from the SynVow prompt controllers, but use the
APIYi OpenAI-compatible chat endpoint and the same Bearer-token style as the
existing Luck image nodes.
"""

import hashlib
import json
import pathlib
import re
import time
import uuid

import requests

from .gpt_2_0_node import API_BASE_URLS, tensor_to_data_url
from .gpt_2_0_node import emit_runtime_status

try:
    import server
    from aiohttp import web
    from nodes import interrupt_processing
except Exception:
    server = None
    web = None

    def interrupt_processing():
        return None


PROMPT_MODEL_OPTIONS = [
    "gemini-3.5-flash",
    "gpt-5.5",
    "gpt-4o",
    "gpt-4.1-mini",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

LUCK_PROMPT_CATEGORY = "Comfyui-Luck/gpt-2.0/文本"
PROMPT_ASPECT_RATIO_OPTIONS = [
    "auto",
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
_PROMPT_DIR = pathlib.Path(__file__).parent / "prompts"

_REFERENCE_SYSTEM_PROMPT = (_PROMPT_DIR / "reference_image_optimizer_system.txt").read_text(encoding="utf-8-sig")
_SCHEMA_PARSER_PROMPT = (_PROMPT_DIR / "gpt-image-2_schema_parser_v1.txt").read_text(encoding="utf-8-sig")
_RENDERER_PROMPT = (_PROMPT_DIR / "gpt-image-2_prompt_renderer_v1.txt").read_text(encoding="utf-8-sig")

_REFERENCE_MODE_MAP = {
    "自动判断": "auto",
    "综合参考": "full_reference",
    "只参考风格": "style_only",
    "只参考构图": "composition_only",
    "只参考色彩光影": "color_lighting_only",
    "只参考版式": "layout_only",
}

_LANDSCAPE = {"16:9", "4:3", "3:2", "2:1", "21:9", "3:1", "4:1", "8:1"}
_PORTRAIT = {"9:16", "3:4", "2:3", "1:2", "9:21", "1:3", "1:4", "1:8"}
_SQUARE = {"1:1"}


def _chat_url(api_base):
    base = (api_base or "https://api.apiyi.com").strip().rstrip("/")
    if base.endswith("/v1/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _api_headers(api_key):
    key = (api_key or "").strip()
    if not key:
        raise ValueError("API Key 不能为空")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _extract_chat_content(data):
    try:
        choices = data.get("choices") or []
        message = choices[0].get("message") or {}
        content = message.get("content", "")
    except Exception as exc:
        raise RuntimeError(f"API 响应格式异常: {str(data)[:500]}") from exc

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content or "")


def _call_apiyi_chat(api_base, api_key, model, messages, timeout_seconds=600):
    actual_model = model or PROMPT_MODEL_OPTIONS[0]
    payload = {
        "model": actual_model,
        "messages": messages,
        "stream": False,
    }
    response = requests.post(
        _chat_url(api_base),
        headers=_api_headers(api_key),
        json=payload,
        timeout=(30, int(timeout_seconds)),
    )
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        body = response.text[:2000] if response.text else "<empty response>"
        raise RuntimeError(f"API易请求失败: HTTP {response.status_code}; response={body}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"API易返回非 JSON: {response.text[:1000]}") from exc

    raw = _extract_chat_content(data).strip()
    if not raw:
        raise RuntimeError(f"模型未返回有效内容: {str(data)[:500]}")
    return raw, data


def _parse_tagged_output(raw):
    def extract(tag):
        pattern = rf"{tag}:\s*(.*?)(?=\n\w+_\w+:|$)"
        match = re.search(pattern, raw, re.DOTALL)
        return match.group(1).strip() if match else ""

    optimized_prompt = extract("optimized_prompt")
    reference_summary = extract("reference_summary")
    return optimized_prompt, reference_summary


def _build_reference_message(ref_urls, user_prompt, reference_mode, target_aspect_ratio, subject_url=None):
    content = []
    if subject_url is not None:
        content.append({"type": "text", "text": "以下是 subject_image（主体图）："})
        content.append({"type": "image_url", "image_url": {"url": subject_url}})
    content.append({
        "type": "text",
        "text": (
            f"以下是 {len(ref_urls)} 张 reference_image（参考图）。请综合分析这些参考图的构图、光影、色彩、"
            "人物/产品关系、画面风格、文字版式和共同视觉规律；如果多张图存在差异，请优先提炼可迁移的共性，"
            "不要机械拼接互相冲突的细节。"
        ),
    })
    for index, ref_url in enumerate(ref_urls, start=1):
        content.append({"type": "text", "text": f"reference_image_{index:02d}："})
        content.append({"type": "image_url", "image_url": {"url": ref_url}})
    has_subject = "是" if subject_url is not None else "否"
    content.append({
        "type": "text",
        "text": (
            f"用户需求：{user_prompt}\n"
            f"是否提供 subject_image：{has_subject}\n"
            f"reference_image_count：{len(ref_urls)}\n"
            f"reference_mode：{reference_mode}\n"
            f"target_aspect_ratio：{target_aspect_ratio}"
        ),
    })
    return content


def _clean_json_block(raw):
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    return text


def _parse_json_response(raw):
    text = _clean_json_block(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"schema 解析失败，模型输出非 JSON: {raw[:500]}")


def _ratio_to_direction(aspect_ratio):
    if aspect_ratio in _LANDSCAPE:
        return "横版构图"
    if aspect_ratio in _PORTRAIT:
        return "竖版构图"
    if aspect_ratio in _SQUARE:
        return "方形构图"
    return "由画面内容决定"


def _build_input_payload(layout_type, optimize_strength, aspect_ratio, user_prompt, exact_text, text_policy):
    return {
        "layout_type": layout_type,
        "optimize_strength": optimize_strength,
        "aspect_ratio": aspect_ratio,
        "direction": _ratio_to_direction(aspect_ratio),
        "user_prompt": user_prompt or "",
        "exact_text": exact_text or "",
        "text_policy": text_policy,
    }


_BANNED_TEXT_PHRASES = [
    "预留标题", "标题展示", "展示标题", "显示标题",
    "预留文字", "文字展示", "展示文字", "添加文案",
    "按钮文字", "具体文案", "标题区", "卖点栏", "品牌区", "信息栏",
    "主标题", "副标题", "卖点", "文字", "文案", "标签",
]


def _remove_text_hints(schema):
    for key in ["composition", "ui_layout", "constraints", "layout_plan", "information_hierarchy"]:
        value = schema.get(key)
        if isinstance(value, str):
            for phrase in _BANNED_TEXT_PHRASES:
                value = value.replace(phrase, "")
            schema[key] = value.strip(" ，,；;。")
        elif isinstance(value, list):
            schema[key] = [item for item in value if not any(phrase in str(item) for phrase in _BANNED_TEXT_PHRASES)]
    schema["text_requirements"] = []
    schema["typography_plan"] = ""
    schema["copy_strategy"] = ""
    return schema


def _normalize_schema(schema, aspect_ratio, exact_text, text_policy, optimize_strength="", layout_type=""):
    schema["aspect_ratio"] = aspect_ratio
    schema["direction"] = _ratio_to_direction(aspect_ratio)
    schema["text_policy"] = text_policy
    schema["optimize_strength"] = optimize_strength
    schema["layout_type"] = layout_type

    if not isinstance(schema.get("constraints"), list):
        schema["constraints"] = []
    schema["constraints"] = schema["constraints"][:3]

    if not isinstance(schema.get("named_entities"), list):
        schema["named_entities"] = []

    exact = exact_text.strip() if exact_text else ""
    if text_policy == "none":
        schema = _remove_text_hints(schema)
    elif text_policy == "preserve":
        schema["text_requirements"] = [exact] if exact else []
    elif text_policy == "enhance":
        if not schema.get("text_requirements"):
            schema["text_requirements"] = [exact] if exact else []
    elif text_policy != "generate":
        schema["text_requirements"] = [exact] if exact else schema.get("text_requirements", [])

    return schema


class LuckReferenceImagePromptOptimizer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key (API密钥)": ("STRING", {"default": "", "multiline": False}),
                "api_base (接口域名)": (API_BASE_URLS, {"default": "https://api.apiyi.com"}),
                "reference_image_01": ("IMAGE",),
                "user_prompt": ("STRING", {"multiline": True, "default": ""}),
                "reference_mode": (
                    ["自动判断", "综合参考", "只参考风格", "只参考构图", "只参考色彩光影", "只参考版式"],
                    {"default": "自动判断"},
                ),
                "target_aspect_ratio": (
                    PROMPT_ASPECT_RATIO_OPTIONS,
                    {"default": "auto"},
                ),
                "model": (PROMPT_MODEL_OPTIONS, {"default": "gemini-3.5-flash"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647, "control_after_generate": True}),
                "timeout_seconds (超时秒数)": ("INT", {"default": 600, "min": 30, "max": 1800}),
            },
            "optional": {
                "reference_image_02": ("IMAGE",),
                "reference_image_03": ("IMAGE",),
                "reference_image_04": ("IMAGE",),
                "reference_image_05": ("IMAGE",),
                "subject_image": ("IMAGE",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("optimized_prompt", "reference_summary")
    FUNCTION = "optimize"
    CATEGORY = LUCK_PROMPT_CATEGORY
    DESCRIPTION = "图生图提示词控制器：API易多模态模型 + 参考图 + 可选主体图 → 结构化生图提示词"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        key = json.dumps(
            {
                k: str(v)
                for k, v in kwargs.items()
                if k not in (
                    "reference_image_01",
                    "reference_image",
                    "reference_image_02",
                    "reference_image_03",
                    "reference_image_04",
                    "reference_image_05",
                    "subject_image",
                    "api_key (API密钥)",
                )
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.md5(key.encode()).hexdigest()

    def optimize(self, reference_image_01, user_prompt, reference_mode, target_aspect_ratio,
                 model, seed=0, subject_image=None, **kwargs):
        api_key = kwargs.get("api_key (API密钥)", "")
        api_base = kwargs.get("api_base (接口域名)", "https://api.apiyi.com")
        timeout_seconds = kwargs.get("timeout_seconds (超时秒数)", 600)
        unique_id = kwargs.get("unique_id")
        start_ts = time.time()
        ref_mode_en = _REFERENCE_MODE_MAP.get(reference_mode, reference_mode)

        try:
            emit_runtime_status(unique_id, "running", "准备参考图", 0.0, 1, 1, timeout_seconds)
            reference_images = [reference_image_01]
            for key in ("reference_image_02", "reference_image_03", "reference_image_04", "reference_image_05"):
                image = kwargs.get(key)
                if image is not None:
                    reference_images.append(image)

            ref_urls = [tensor_to_data_url(image) for image in reference_images]
            subject_url = tensor_to_data_url(subject_image) if subject_image is not None else None
            user_content = _build_reference_message(
                ref_urls,
                user_prompt,
                ref_mode_en,
                target_aspect_ratio,
                subject_url=subject_url,
            )
            messages = [
                {"role": "system", "content": _REFERENCE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            emit_runtime_status(
                unique_id,
                "running",
                f"分析 {len(ref_urls)} 张参考图",
                time.time() - start_ts,
                1,
                1,
                timeout_seconds,
            )
            print(f"[Luck Reference Prompt Optimizer] {model} 正在生成，reference_images={len(ref_urls)}, seed={seed} (not sent to API)")
            raw, _ = _call_apiyi_chat(api_base, api_key, model, messages, timeout_seconds)
            emit_runtime_status(unique_id, "running", "解析提示词", time.time() - start_ts, 1, 1, timeout_seconds)
            optimized_prompt, reference_summary = _parse_tagged_output(raw)
            if not optimized_prompt:
                optimized_prompt = raw
            elapsed = time.time() - start_ts
            emit_runtime_status(unique_id, "success", f"提示词生成完成 (耗时 {elapsed:.1f}s)", elapsed, 1, 1, timeout_seconds)
            return (optimized_prompt, reference_summary)
        except Exception as exc:
            emit_runtime_status(unique_id, "error", str(exc), time.time() - start_ts, 1, 1, timeout_seconds)
            raise


class LuckGPTImage2PromptOptimizer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key (API密钥)": ("STRING", {"default": "", "multiline": False}),
                "api_base (接口域名)": (API_BASE_URLS, {"default": "https://api.apiyi.com"}),
                "user_prompt": ("STRING", {"multiline": True, "default": ""}),
                "layout_type": (
                    ["自动判断", "纯画面", "图文混排海报", "电商主图", "社媒封面"],
                    {"default": "自动判断"},
                ),
                "text_policy": (
                    ["不加文字", "保留原文", "优化原文", "自动生成"],
                    {"default": "保留原文"},
                ),
                "model": (PROMPT_MODEL_OPTIONS, {"default": "gemini-3.5-flash"}),
                "optimize_strength": (["标准", "增强"], {"default": "标准"}),
                "aspect_ratio": (
                    PROMPT_ASPECT_RATIO_OPTIONS,
                    {"default": "16:9"},
                ),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647, "control_after_generate": True}),
                "timeout_seconds (超时秒数)": ("INT", {"default": 600, "min": 30, "max": 1800}),
                "exact_text": ("STRING", {"multiline": True, "default": ""}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("optimized_prompt", "debug_info")
    FUNCTION = "optimize"
    CATEGORY = LUCK_PROMPT_CATEGORY
    DESCRIPTION = "使用 API易多模态/文本模型优化 GPT-Image-2 图像生成提示词"

    _TEXT_POLICY_MAP = {"不加文字": "none", "保留原文": "preserve", "优化原文": "enhance", "自动生成": "generate"}
    _STRENGTH_MAP = {"light": "标准", "standard": "标准", "strong": "增强"}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        key = json.dumps(
            {k: v for k, v in kwargs.items() if k != "api_key (API密钥)"},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.md5(key.encode()).hexdigest()

    def optimize(self, user_prompt, layout_type, text_policy, model, optimize_strength,
                 aspect_ratio="16:9", seed=0, exact_text="", **kwargs):
        api_key = kwargs.get("api_key (API密钥)", "")
        api_base = kwargs.get("api_base (接口域名)", "https://api.apiyi.com")
        timeout_seconds = kwargs.get("timeout_seconds (超时秒数)", 600)
        unique_id = kwargs.get("unique_id")
        start_ts = time.time()
        optimize_strength = self._STRENGTH_MAP.get(optimize_strength, optimize_strength)
        text_policy = self._TEXT_POLICY_MAP.get(text_policy, text_policy)
        exact_text = exact_text or ""

        try:
            emit_runtime_status(unique_id, "running", "解析需求结构", 0.0, 1, 2, timeout_seconds)
            payload = _build_input_payload(layout_type, optimize_strength, aspect_ratio, user_prompt, exact_text, text_policy)
            schema_messages = [
                {"role": "system", "content": _SCHEMA_PARSER_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            print(f"[Luck GPT-Image-2 Prompt Optimizer] {model} schema 阶段生成中，seed={seed} (not sent to API)")
            schema_raw, _ = _call_apiyi_chat(api_base, api_key, model, schema_messages, timeout_seconds)
            emit_runtime_status(unique_id, "running", "整理 Schema", time.time() - start_ts, 1, 2, timeout_seconds)
            schema = _parse_json_response(schema_raw)
            schema = _normalize_schema(schema, aspect_ratio, exact_text, text_policy, optimize_strength, layout_type)

            renderer_messages = [
                {"role": "system", "content": _RENDERER_PROMPT},
                {"role": "user", "content": json.dumps(schema, ensure_ascii=False)},
            ]
            emit_runtime_status(unique_id, "running", "渲染最终提示词", time.time() - start_ts, 2, 2, timeout_seconds)
            print(f"[Luck GPT-Image-2 Prompt Optimizer] {model} 渲染阶段生成中")
            optimized, _ = _call_apiyi_chat(api_base, api_key, model, renderer_messages, timeout_seconds)

            if optimize_strength == "增强" and text_policy == "generate":
                optimized = optimized.replace("【限制条件】", "【创作自由】")
            if optimize_strength == "标准" and text_policy == "generate":
                texts = schema.get("text_requirements", [])
                text_list = "、".join([f"\"{t}\"" for t in texts])
                strict_text_block = (
                    f"画面必须且只能显示以下文字：{text_list}。\n"
                    "不得出现除此之外的任何可读文字、装饰文字、章印文字、小标签、英文补充或无意义文字。"
                    "文字应清晰、准确、层级明确，排版稳定，不做创意发散。"
                )
                optimized = re.sub(
                    r"【文字要求】.*?(?=【|$)",
                    f"【文字要求】\n{strict_text_block}\n",
                    optimized,
                    flags=re.DOTALL,
                )

            direction = _ratio_to_direction(aspect_ratio)
            debug_info = (
                f"model={model}\n"
                f"api_base={api_base}\n"
                f"layout_type={layout_type}\n"
                f"optimize_strength={optimize_strength}\n"
                f"aspect_ratio={aspect_ratio}\n"
                f"direction={direction}\n"
                f"text_policy={text_policy}\n"
                f"has_exact_text={str(bool(exact_text.strip())).lower()}\n"
                f"seed={seed}\n"
                f"resolved_layout_type={schema.get('image_type', '')}\n"
                f"resolved_text_policy={schema.get('text_policy', '')}\n"
                f"schema_result={json.dumps(schema, ensure_ascii=False)}\n"
                f"renderer_input={json.dumps(schema, ensure_ascii=False)}\n"
                f"final_prompt={optimized}"
            )
            elapsed = time.time() - start_ts
            emit_runtime_status(unique_id, "success", f"提示词生成完成 (耗时 {elapsed:.1f}s)", elapsed, 2, 2, timeout_seconds)
            return (optimized, debug_info)
        except Exception as exc:
            emit_runtime_status(unique_id, "error", str(exc), time.time() - start_ts, 1, 2, timeout_seconds)
            raise


_pending_text_lists = {}


class LuckTextListEditor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text_list": ("STRING", {"forceInput": True}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("edited_text", "edited_texts")
    INPUT_IS_LIST = True
    OUTPUT_IS_LIST = (False, True)
    FUNCTION = "edit_text_list"
    CATEGORY = LUCK_PROMPT_CATEGORY

    def edit_text_list(self, text_list, unique_id=None):
        if server is None or server.PromptServer.instance is None:
            raise RuntimeError("文本停留编辑器需要在 ComfyUI 服务环境中运行")

        if isinstance(unique_id, list):
            unique_id = unique_id[0] if unique_id else None

        texts = text_list if isinstance(text_list, list) else [str(text_list)]
        cleaned_texts = [str(t).strip() for t in texts]
        session_id = str(uuid.uuid4())
        _pending_text_lists[session_id] = {
            "edited_texts": cleaned_texts.copy(),
            "confirmed": False,
            "cancelled": False,
        }

        server.PromptServer.instance.send_sync(
            "luck_text_list_edit_session",
            {
                "session_id": session_id,
                "node_id": unique_id,
                "texts": cleaned_texts,
            },
        )

        timeout = 3600
        start_time = time.time()
        while True:
            time.sleep(0.1)
            if session_id not in _pending_text_lists:
                interrupt_processing()
                return ("", [])

            session = _pending_text_lists[session_id]
            if session.get("confirmed"):
                break
            if session.get("cancelled"):
                del _pending_text_lists[session_id]
                interrupt_processing()
                return ("", [])
            if time.time() - start_time > timeout:
                del _pending_text_lists[session_id]
                interrupt_processing()
                return ("", [])

        edited_texts = _pending_text_lists[session_id]["edited_texts"]
        if not isinstance(edited_texts, list):
            edited_texts = [edited_texts] if edited_texts else []
        del _pending_text_lists[session_id]
        edited_text = "\n".join(str(text).strip() for text in edited_texts if str(text).strip())
        return (edited_text, edited_texts)


def _add_text_editor_routes(routes):
    @routes.post("/luck_text_list_edit/confirm")
    async def confirm(request):
        try:
            data = await request.json()
            session_id = data.get("session_id")
            edited_texts = data.get("edited_texts", [])

            if session_id not in _pending_text_lists:
                return web.json_response({"status": "error", "message": "Session not found"}, status=404)

            if not isinstance(edited_texts, list):
                edited_texts = [edited_texts] if edited_texts else []

            _pending_text_lists[session_id]["edited_texts"] = edited_texts
            _pending_text_lists[session_id]["confirmed"] = True
            return web.json_response({"status": "success"})
        except Exception as exc:
            print(f"LuckTextListEditor: confirm error: {exc}")
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    @routes.post("/luck_text_list_edit/cancel")
    async def cancel(request):
        try:
            data = await request.json()
            session_id = data.get("session_id")

            if session_id not in _pending_text_lists:
                return web.json_response({"status": "error", "message": "Session not found"}, status=404)

            _pending_text_lists[session_id]["cancelled"] = True
            return web.json_response({"status": "success"})
        except Exception as exc:
            print(f"LuckTextListEditor: cancel error: {exc}")
            return web.json_response({"status": "error", "message": str(exc)}, status=500)


try:
    if server is not None and web is not None and server.PromptServer.instance is not None:
        _add_text_editor_routes(server.PromptServer.instance.routes)
except Exception as exc:
    print(f"Warning: Could not register LuckTextListEditor routes: {exc}")


NODE_CLASS_MAPPINGS = {
    "LuckReferenceImagePromptOptimizer": LuckReferenceImagePromptOptimizer,
    "LuckGPTImage2PromptOptimizer": LuckGPTImage2PromptOptimizer,
    "LuckTextListEditor": LuckTextListEditor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LuckReferenceImagePromptOptimizer": "图生图提示词控制器",
    "LuckGPTImage2PromptOptimizer": "GPT-Image-2 文生图提示词控制器",
    "LuckTextListEditor": "文本停留编辑器",
}
