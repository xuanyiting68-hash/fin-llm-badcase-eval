"""通过官方 API 采集各模型对题库的回答。

用法（在仓库根目录运行）:
    python scripts/collect.py --dry-run                 # 只检查配置和 Key，不发请求
    python scripts/collect.py --models deepseek --ids A01   # 先用 1 道题试通
    python scripts/collect.py                           # 全部模型 × 全部题目
    python scripts/collect.py --models kimi --force     # 重新采集（覆盖已有回答）

输出:
    responses/<模型>/<题号>.md            回答正文 + 元数据（用于打分）
    responses/<模型>/<题号>.reasoning.md  思考过程（有的话，用于根因分析）
    responses/<模型>/raw/<题号>.json      原始元数据（不含 API Key）
    responses/collect_log.csv             每次调用的记录
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scripts" / "models_config.json"
QUESTIONS = ROOT / "data" / "questions.jsonl"
OUT = ROOT / "responses"
CST = timezone(timedelta(hours=8))
MAX_RETRIES = 4
TIMEOUT_SEC = 600


def load_env(path: Path) -> None:
    """读取 .env（KEY=VALUE 格式），不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_questions(ids: list[str] | None) -> list[dict]:
    qs = [json.loads(l) for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()]
    if ids:
        wanted = {i.upper() for i in ids}
        qs = [q for q in qs if q["id"] in wanted]
        missing = wanted - {q["id"] for q in qs}
        if missing:
            sys.exit(f"题号不存在: {', '.join(sorted(missing))}")
    return qs


def call_model(client, cfg: dict, question: str) -> dict:
    """流式调用，汇总正文、思考过程和 token 用量。"""
    kwargs = dict(
        model=cfg["model"],
        messages=[{"role": "user", "content": question}],
        stream=True,
        stream_options={"include_usage": True},
        **cfg.get("params", {}),
    )
    if cfg.get("extra_body"):
        kwargs["extra_body"] = cfg["extra_body"]

    content, reasoning, usage, returned_model, finish = [], [], None, None, None
    t0 = time.time()
    for chunk in client.chat.completions.create(**kwargs):
        returned_model = getattr(chunk, "model", None) or returned_model
        if getattr(chunk, "usage", None):
            usage = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else dict(chunk.usage)
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        if getattr(delta, "content", None):
            content.append(delta.content)
        rc = getattr(delta, "reasoning_content", None)
        if rc is None and getattr(delta, "model_extra", None):
            rc = delta.model_extra.get("reasoning_content")
        if rc:
            reasoning.append(rc)
        if choice.finish_reason:
            finish = choice.finish_reason
    return {
        "content": "".join(content).strip(),
        "reasoning": "".join(reasoning).strip(),
        "usage": usage,
        "returned_model": returned_model,
        "finish_reason": finish,
        "latency_sec": round(time.time() - t0, 1),
    }


def is_retryable(err: Exception) -> bool:
    status = getattr(err, "status_code", None)
    if status is not None:
        return status == 429 or status >= 500
    name = type(err).__name__
    return name in {"APIConnectionError", "APITimeoutError", "RateLimitError"}


def write_outputs(name: str, cfg: dict, q: dict, res: dict, collected_at: str) -> Path:
    d = OUT / name
    (d / "raw").mkdir(parents=True, exist_ok=True)
    usage = res["usage"] or {}
    header = [
        "---",
        f"question_id: {q['id']}",
        f"model_key: {name}",
        f"model_requested: {cfg['model']}",
        f"model_returned: {res['returned_model']}",
        f"collected_at: {collected_at}",
        "method: API",
        "web_search: off",
        f"thinking: {cfg.get('thinking', '')}",
        "temperature: 接口默认（思考模式下不可设置或不生效）",
        f"finish_reason: {res['finish_reason']}",
        f"prompt_tokens: {usage.get('prompt_tokens')}",
        f"completion_tokens: {usage.get('completion_tokens')}",
        f"latency_sec: {res['latency_sec']}",
        "---",
        "",
        "## 问题",
        "",
        q["question"],
        "",
        "## 回答",
        "",
        res["content"] or "（空回答）",
        "",
    ]
    path = d / f"{q['id']}.md"
    path.write_text("\n".join(header), encoding="utf-8")
    if res["reasoning"]:
        (d / f"{q['id']}.reasoning.md").write_text(
            f"# {q['id']} · {cfg['display_name']} · 思考过程\n\n{res['reasoning']}\n", encoding="utf-8"
        )
    meta = {k: v for k, v in res.items() if k not in ("content", "reasoning")}
    meta.update(question_id=q["id"], model_key=name, model_requested=cfg["model"],
                collected_at=collected_at, reasoning_chars=len(res["reasoning"]))
    (d / "raw" / f"{q['id']}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def log_row(row: dict) -> None:
    path = OUT / "collect_log.csv"
    new = not path.exists()
    OUT.mkdir(exist_ok=True)
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser(description="采集模型回答")
    ap.add_argument("--models", nargs="*", help="模型 key，如 deepseek doubao qwen kimi；默认全部")
    ap.add_argument("--ids", nargs="*", help="题号，如 A01 G03；默认全部")
    ap.add_argument("--force", action="store_true", help="覆盖已有回答")
    ap.add_argument("--dry-run", action="store_true", help="只检查配置，不发请求")
    args = ap.parse_args()

    load_env(ROOT / ".env")
    config = {k: v for k, v in json.loads(CONFIG.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    names = args.models or list(config)
    unknown = [n for n in names if n not in config]
    if unknown:
        sys.exit(f"未知模型: {unknown}；可选: {list(config)}")
    questions = load_questions(args.ids)

    # 检查 Key
    ready = []
    for n in names:
        cfg = config[n]
        key = os.environ.get(cfg["key_env"], "")
        base = os.environ.get(cfg.get("base_url_env", ""), "") or cfg["base_url"]
        status = "OK" if key else f"缺少 {cfg['key_env']}"
        print(f"[{n:8}] model={cfg['model']:<22} base={base}  key: {status}")
        if key:
            ready.append((n, cfg, key, base))
    if args.dry_run:
        print(f"\n题目 {len(questions)} 道，可用模型 {len(ready)}/{len(names)}。dry-run 结束，未发请求。")
        return
    if not ready:
        sys.exit("没有可用的 API Key，请先填写 .env")

    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("缺少 openai 包，请先运行: pip install -r requirements.txt")

    total, done, failed = len(ready) * len(questions), 0, []
    for n, cfg, key, base in ready:
        client = OpenAI(api_key=key, base_url=base, timeout=TIMEOUT_SEC, max_retries=0)
        last_call = 0.0
        for q in questions:
            target = OUT / n / f"{q['id']}.md"
            if target.exists() and not args.force:
                done += 1
                print(f"[{done}/{total}] {n} {q['id']} 已存在，跳过")
                continue
            for attempt in range(1, MAX_RETRIES + 1):
                wait = cfg.get("min_interval_sec", 1) - (time.time() - last_call)
                if wait > 0:
                    time.sleep(wait)
                last_call = time.time()
                collected_at = datetime.now(CST).isoformat(timespec="seconds")
                try:
                    res = call_model(client, cfg, q["question"])
                    path = write_outputs(n, cfg, q, res, collected_at)
                    done += 1
                    u = res["usage"] or {}
                    print(f"[{done}/{total}] {n} {q['id']} OK  {res['latency_sec']}s  "
                          f"tokens={u.get('completion_tokens')}  -> {path.relative_to(ROOT)}")
                    log_row({"collected_at": collected_at, "model_key": n, "question_id": q["id"],
                             "status": "ok", "model_returned": res["returned_model"],
                             "finish_reason": res["finish_reason"], "latency_sec": res["latency_sec"],
                             "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                             "error": ""})
                    break
                except Exception as e:  # noqa: BLE001
                    msg = f"{type(e).__name__}: {str(e)[:300]}"
                    if attempt < MAX_RETRIES and is_retryable(e):
                        backoff = 10 * 2 ** (attempt - 1)
                        print(f"  {n} {q['id']} 第 {attempt} 次失败（{msg}），{backoff}s 后重试")
                        time.sleep(backoff)
                        continue
                    print(f"  {n} {q['id']} 失败: {msg}")
                    failed.append((n, q["id"], msg))
                    log_row({"collected_at": collected_at, "model_key": n, "question_id": q["id"],
                             "status": "error", "model_returned": "", "finish_reason": "", "latency_sec": "",
                             "prompt_tokens": "", "completion_tokens": "", "error": msg})
                    break

    print(f"\n完成 {done}/{total}，失败 {len(failed)}。")
    for n, qid, msg in failed:
        print(f"  - {n} {qid}: {msg}")
    if failed:
        print("失败的题可重跑同一命令，已成功的会自动跳过。")


if __name__ == "__main__":
    main()
