import { app } from "../../../scripts/app.js";

const EXTENSION_NAME = "comfyui_luck_gpt_response.password_widget";
const API_KEY_WIDGET_NAME = "api_key (API密钥)";
const TARGET_NODE_TYPES = new Set([
    "ComfyuiLuckGPTResponseNode",
    "ComfyuiLuckGPTImage2Node",
    "LuckReferenceImagePromptOptimizer",
    "LuckGPTImage2PromptOptimizer",
]);

let styleInjected = false;

function injectStyle() {
    if (styleInjected || document.getElementById("comfyui-luck-password-widget-style")) {
        styleInjected = true;
        return;
    }

    const style = document.createElement("style");
    style.id = "comfyui-luck-password-widget-style";
    style.textContent = [
        ".comfyui-luck-password-widget {",
        "    --comfy-widget-min-height: 34px;",
        "    --comfy-widget-max-height: 34px;",
        "    --comfy-widget-height: 34px;",
        "    box-sizing: border-box;",
        "    width: 100%;",
        "    min-height: 34px;",
        "    display: grid;",
        "    grid-template-columns: auto minmax(0, 1fr) auto;",
        "    align-items: center;",
        "    gap: 7px;",
        "    padding: 2px 0;",
        "    color: var(--input-text, #ddd);",
        "    font: 12px sans-serif;",
        "}",
        ".comfyui-luck-password-widget__label {",
        "    white-space: nowrap;",
        "    user-select: none;",
        "}",
        ".comfyui-luck-password-widget__input {",
        "    box-sizing: border-box;",
        "    width: 100%;",
        "    min-width: 0;",
        "    height: 28px;",
        "    padding: 4px 8px;",
        "    border: 1px solid rgba(255, 255, 255, 0.2);",
        "    border-radius: 6px;",
        "    outline: none;",
        "    background: var(--comfy-input-bg, rgba(0, 0, 0, 0.28));",
        "    color: var(--input-text, #eee);",
        "}",
        ".comfyui-luck-password-widget__input:focus {",
        "    border-color: var(--p-primary-color, #5da9e9);",
        "}",
        ".comfyui-luck-password-widget__toggle {",
        "    box-sizing: border-box;",
        "    height: 28px;",
        "    min-width: 46px;",
        "    padding: 0 7px;",
        "    border: 1px solid rgba(255, 255, 255, 0.2);",
        "    border-radius: 6px;",
        "    background: var(--comfy-input-bg, rgba(0, 0, 0, 0.28));",
        "    color: var(--input-text, #eee);",
        "    cursor: pointer;",
        "}",
        ".comfyui-luck-password-widget__toggle:hover {",
        "    background: rgba(255, 255, 255, 0.12);",
        "}",
    ].join("\n");
    document.head.appendChild(style);
    styleInjected = true;
}

function markDirty(node) {
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

function replaceApiKeyWidget(node) {
    if (node.__comfyuiLuckPasswordWidgetInstalled || !Array.isArray(node.widgets)) {
        return false;
    }

    const widgetIndex = node.widgets.findIndex((widget) => widget?.name === API_KEY_WIDGET_NAME);
    if (widgetIndex < 0) {
        return false;
    }

    const originalWidget = node.widgets[widgetIndex];
    if (originalWidget?.__comfyuiLuckPasswordWidget) {
        node.__comfyuiLuckPasswordWidgetInstalled = true;
        return true;
    }

    injectStyle();

    const container = document.createElement("div");
    container.className = "comfyui-luck-password-widget";

    const label = document.createElement("span");
    label.className = "comfyui-luck-password-widget__label";
    label.textContent = "API Key";
    container.appendChild(label);

    const input = document.createElement("input");
    input.className = "comfyui-luck-password-widget__input";
    input.type = "password";
    input.autocomplete = "off";
    input.autocapitalize = "off";
    input.spellcheck = false;
    input.placeholder = "留空时使用 OPENAI_API_KEY";
    input.value = String(originalWidget?.value ?? "");
    input.setAttribute("aria-label", API_KEY_WIDGET_NAME);
    container.appendChild(input);

    const toggle = document.createElement("button");
    toggle.className = "comfyui-luck-password-widget__toggle";
    toggle.type = "button";
    container.appendChild(toggle);

    let revealed = false;
    const renderVisibility = () => {
        input.type = revealed ? "text" : "password";
        toggle.textContent = revealed ? "隐藏" : "显示";
        toggle.title = revealed ? "隐藏 API Key" : "显示 API Key";
        toggle.setAttribute("aria-pressed", String(revealed));
        toggle.setAttribute("aria-label", toggle.title);
    };
    renderVisibility();

    toggle.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
    });
    toggle.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        revealed = !revealed;
        renderVisibility();
        input.focus({ preventScroll: true });
        input.setSelectionRange(input.value.length, input.value.length);
    });

    const initialValue = input.value;
    const originalOptions = originalWidget?.options || {};
    const originalCallback = originalWidget?.callback;
    const originalTooltip = originalWidget?.tooltip;

    originalWidget?.onRemove?.();
    node.widgets.splice(widgetIndex, 1);

    const passwordWidget = node.addDOMWidget(
        API_KEY_WIDGET_NAME,
        "comfyui_luck_password",
        container,
        {
            ...originalOptions,
            hideOnZoom: false,
            getMinHeight: () => 34,
            getMaxHeight: () => 34,
            getValue: () => input.value,
            setValue: (value) => {
                input.value = value == null ? "" : String(value);
            },
        }
    );

    const appendedIndex = node.widgets.indexOf(passwordWidget);
    if (appendedIndex >= 0) {
        node.widgets.splice(appendedIndex, 1);
        node.widgets.splice(widgetIndex, 0, passwordWidget);
    }

    passwordWidget.callback = originalCallback;
    passwordWidget.tooltip = originalTooltip || "输入框为空时读取环境变量 OPENAI_API_KEY";
    passwordWidget.__comfyuiLuckPasswordWidget = true;
    passwordWidget.value = initialValue;

    input.addEventListener("input", () => {
        passwordWidget.value = input.value;
        markDirty(node);
    });

    node.__comfyuiLuckPasswordWidgetInstalled = true;
    node.__comfyuiLuckPasswordWidget = passwordWidget;
    markDirty(node);
    return true;
}

app.registerExtension({
    name: EXTENSION_NAME,
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!TARGET_NODE_TYPES.has(nodeData?.name)) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            if (!replaceApiKeyWidget(this)) {
                queueMicrotask(() => replaceApiKeyWidget(this));
            }
            return result;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            replaceApiKeyWidget(this);
            return result;
        };
    },
});
