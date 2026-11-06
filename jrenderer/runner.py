"""批量执行：并发、重试、断点续跑、manifest 落盘。"""

import csv
import random
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .providers.base import ProviderError

MANIFEST_NAME = "manifest.csv"
FIELDS = [
    "idx", "status", "file", "piece", "metal_key", "metal_zh", "gem_key", "gem_zh",
    "angle_key", "angle_zh", "variant", "provider", "model", "latency_ms", "attempts",
    "error", "note", "prompt",
]


class Manifest:
    """每次运行后整体重写，保证中断后重新跑也能得到完整对账表。"""

    def __init__(self, path: Path):
        self.path = path
        self.rows: dict[str, dict] = {}
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if row.get("file"):
                        self.rows[row["file"]] = {k: row.get(k, "") for k in FIELDS}

    def put(self, row: dict) -> None:
        self.rows[row["file"]] = {k: str(row.get(k, "")) for k in FIELDS}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted(self.rows.values(), key=lambda r: int(r["idx"]) if str(r.get("idx", "")).isdigit() else 10**9)
        tmp = self.path.with_suffix(".csv.part")
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(self.path)


def _row(job, provider, status, latency_ms=0, attempts=0, error="", note=""):
    return {
        "idx": job.index,
        "status": status,
        "file": job.out_path.name,
        "piece": job.piece_name,
        "metal_key": job.metal_key,
        "metal_zh": job.metal_label,
        "gem_key": job.gem_key,
        "gem_zh": job.gem_label,
        "angle_key": job.angle_key,
        "angle_zh": job.angle_label,
        "variant": job.variant,
        "provider": provider.name,
        "model": provider.model,
        "latency_ms": latency_ms,
        "attempts": attempts,
        "error": error,
        "note": note,
        "prompt": job.prompt,
    }


def _write_image(job, data: bytes) -> None:
    if not data or len(data) < 1024:
        raise ProviderError(f"后端返回的图片数据过小（{len(data)} 字节）", retryable=True)
    job.out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = job.out_path.with_suffix(job.out_path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(job.out_path)


def _one(job, provider, manifest, reference, retries, backoff, force):
    """单任务：重试 → 落盘 → 记账。返回最终状态字符串。"""
    if not force and job.out_path.exists() and job.out_path.stat().st_size > 1024:
        prev = manifest.rows.get(job.out_path.name)
        if prev and prev.get("status") == "ok":
            # 已有成功记录：保留 ok 状态与耗时，只追加说明，避免重跑把已交付的图"洗掉"
            row = dict(prev)
            row["note"] = "已有文件，跳过重跑"
            if prev.get("provider") != provider.name:
                row["note"] += f"（原后端 {prev.get('provider')}）"
            manifest.put(row)
        else:
            manifest.put(_row(job, provider, "skipped", note="本地已存在，跳过"))
        return "skipped"

    attempts = 0
    last_error = ""
    started = time.time()
    while attempts <= retries:
        attempts += 1
        try:
            result = provider.generate(job, reference_image=reference)
            _write_image(job, result.data)
            manifest.put(_row(
                job, provider, "ok",
                latency_ms=int((time.time() - started) * 1000),
                attempts=attempts, note=result.note,
            ))
            return "ok"
        except ProviderError as exc:
            last_error = str(exc)
            if not exc.retryable or attempts > retries:
                break
            delay = backoff * (2 ** (attempts - 1)) + random.uniform(0, 0.6)
            time.sleep(delay)
        except Exception as exc:  # noqa: BLE001  — 单任务异常不能拖垮整批
            last_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=2)}"
            break

    manifest.put(_row(
        job, provider, "failed",
        latency_ms=int((time.time() - started) * 1000),
        attempts=attempts, error=last_error.strip().replace("\n", " | ")[:500],
    ))
    return "failed"


def run(spec, provider, workers: int = 4, retries: int = 2, backoff: float = 2.0,
        limit: int | None = None, force: bool = False, quiet: bool = False) -> dict:
    jobs = spec.jobs[:limit] if limit else spec.jobs
    manifest = Manifest(spec.out_dir / MANIFEST_NAME)
    total = len(jobs)
    stats = {"ok": 0, "failed": 0, "skipped": 0}

    if not quiet:
        print(f"任务数 {total} ｜ 后端 {provider.describe()} ｜ 并发 {workers} ｜ 输出 {spec.out_dir}")

    if total == 0:
        manifest.save()
        return stats

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_one, job, provider, manifest, spec.reference_image, retries, backoff, force): job
            for job in jobs
        }
        for future in as_completed(futures):
            job = futures[future]
            status = future.result()
            stats[status] = stats.get(status, 0) + 1
            done += 1
            if not quiet:
                print(f"[{done}/{total}] {status:<8} {job.out_path.name}")

    manifest.save()
    if not quiet:
        print(f"完成：成功 {stats.get('ok', 0)} ｜ 跳过 {stats.get('skipped', 0)} ｜ 失败 {stats.get('failed', 0)}")
        print(f"对账表：{spec.out_dir / MANIFEST_NAME}")
    return stats
