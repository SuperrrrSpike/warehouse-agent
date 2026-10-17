from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request


def summarize_snapshot(snapshot, provider, mode, config):
    try:
        if provider == "openai" and config.openai_api_key:
            return _summarize_with_openai(snapshot, mode, config)
        if provider == "anthropic" and config.anthropic_api_key:
            return _summarize_with_anthropic(snapshot, mode, config)
    except (urllib.error.URLError, TimeoutError, socket.timeout, json.JSONDecodeError):
        # 报告生成不应因外部摘要服务暂时不可用而失败。
        pass
    return _summarize_locally(snapshot, mode)


def _build_prompt(snapshot, mode):
    return (
        f"你是仓储效率分析助手，请基于以下指标输出一段简洁结论，突出瓶颈、风险与建议。"
        f"输出控制在120字以内。模式：{mode}。"
        f"数据: {json.dumps(snapshot, ensure_ascii=False)}"
    )


def _summarize_locally(snapshot, mode):
    parts = []
    if snapshot["backlog_count"] > 0:
        parts.append(f"当前{mode}存在{snapshot['backlog_count']}个积压任务")
    if snapshot["empty_run_pct"] > 20:
        parts.append(f"空跑比例{snapshot['empty_run_pct']:.1f}%偏高")
    if snapshot["avg_utilization_pct"] < 60:
        parts.append(f"机器人利用率仅{snapshot['avg_utilization_pct']:.1f}%")
    if snapshot["top_congested_stations"]:
        station = snapshot["top_congested_stations"][0]
        parts.append(
            f"{station['station_id']}排队最重，平均等待{station['avg_queue_wait_minutes']:.1f}分钟"
        )
    if not parts:
        parts.append("整体运行平稳，建议继续跟踪站点排队与空跑比例。")
    return "；".join(parts) + "。"


def _openai_response_text(data):
    direct = data.get("output_text") if isinstance(data, dict) else None
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    texts = []
    output = data.get("output", []) if isinstance(data, dict) else []
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    return "\n".join(texts)


def _summarize_with_openai(snapshot, mode, config):
    payload = {
        "model": config.openai_model,
        "input": _build_prompt(snapshot, mode),
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = _openai_response_text(data)
    if text:
        return text
    return _summarize_locally(snapshot, mode)


def _summarize_with_anthropic(snapshot, mode, config):
    payload = {
        "model": config.anthropic_model,
        "max_tokens": 220,
        "messages": [
            {
                "role": "user",
                "content": _build_prompt(snapshot, mode),
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": config.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data.get("content") or []
    texts = [item.get("text", "") for item in content if item.get("type") == "text"]
    text = "".join(texts).strip()
    return text or _summarize_locally(snapshot, mode)
