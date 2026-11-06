"""命令行入口：plan / render / report。"""

import argparse
import csv
import json
import sys
from pathlib import Path

from .providers import get_provider
from .providers.base import ProviderError
from .runner import MANIFEST_NAME, run
from .spec import SpecError, load_spec


def _load(args):
    return load_spec(args.config, out_dir=args.out, variants=args.variants)


def cmd_plan(args):
    spec = _load(args)
    combos = len(spec.metals) * len(spec.gem_specs) * len(spec.angles)
    print(f"单品：{spec.piece_name}")
    print(f"金属 {len(spec.metals)} × 宝石 {len(spec.gem_specs)} × 视角 {len(spec.angles)} "
          f"× 变体 {spec.variants} = {len(spec.jobs)} 张（组合数 {combos}）")
    print(f"输出目录：{spec.out_dir}")
    print(f"尺寸 {spec.size} ｜ 比例 {spec.ratio} ｜ 参考图 {spec.reference_image or '无'}")
    print()
    print(f"{'#':>4}  {'金属':<10} {'宝石':<22} {'视角':<12} 文件")
    shown = len(spec.jobs) if args.show == 0 else min(args.show or 12, len(spec.jobs))
    for job in spec.jobs[:shown]:
        print(f"{job.index:>4}  {job.metal_label:<10} {job.gem_label:<22} {job.angle_label:<12} {job.out_path.name}")
    if len(spec.jobs) > shown:
        print(f"... 其余 {len(spec.jobs) - shown} 张省略（--show 0 可全部列出）")

    if args.prompts:
        path = Path(args.prompts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for job in spec.jobs:
                fh.write(f"### {job.index} {job.out_path.name}\n{job.prompt}\n\n")
        print(f"\n提示词已写到 {path}")

    if args.json:
        data = [
            {"idx": j.index, "file": j.out_path.name, "prompt": j.prompt}
            for j in spec.jobs
        ]
        Path(args.json).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"任务清单已写到 {args.json}")
    return 0


def cmd_render(args):
    spec = _load(args)
    provider = get_provider(args.provider, args.model)

    if args.dry_run:
        print(f"[dry-run] 只演练不调后端：{len(spec.jobs)} 个任务，后端 {provider.describe()}")
        for job in spec.jobs[: args.limit or len(spec.jobs)]:
            print(f"{job.index:>4} {job.out_path.name}")
            print(f"     {job.prompt}")
        return 0

    stats = run(
        spec,
        provider,
        workers=args.workers,
        retries=args.retries,
        backoff=args.backoff,
        limit=args.limit,
        force=args.force,
    )
    return 0 if stats.get("failed", 0) == 0 else 1


def cmd_report(args):
    target = Path(args.dir)
    manifest = target / MANIFEST_NAME
    if not manifest.exists():
        print(f"未找到 {manifest}，请先执行 render", file=sys.stderr)
        return 2

    with manifest.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    by_status = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1

    print(f"清单：{manifest}")
    print(f"总任务 {len(rows)} ｜ " + " ｜ ".join(f"{k} {v}" for k, v in sorted(by_status.items())))

    missing = [r for r in rows if r["status"] == "ok" and not (target / r["file"]).exists()]
    tiny = [r for r in rows if (target / r["file"]).exists() and (target / r["file"]).stat().st_size < 1024]
    if missing:
        print(f"\n清单标记成功但文件缺失 {len(missing)} 个：")
        for r in missing[:10]:
            print(f"  #{r['idx']} {r['file']}")
    if tiny:
        print(f"\n文件存在但疑似损坏（<1KB）{len(tiny)} 个：")
        for r in tiny[:10]:
            print(f"  #{r['idx']} {r['file']}")

    failed = [r for r in rows if r["status"] == "failed"]
    if failed:
        print(f"\n失败明细 {len(failed)} 条：")
        for r in failed[:20]:
            print(f"  #{r['idx']} {r['file']}  尝试 {r['attempts']} 次  {r['error'][:160]}")

    present = [r for r in rows if (target / r["file"]).exists() and (target / r["file"]).stat().st_size >= 1024]
    print(f"\n磁盘上可交付 {len(present)} 张（清单标记成功 {by_status.get('ok', 0)} 条）"
          + ("；存在问题，见上方明细" if (missing or tiny or failed) else "，全部校验通过"))
    return 0 if not (missing or tiny) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jrenderer",
        description="珠宝批量效果图渲染管线：一件设计 × 多材质 × 多宝石 × 多视角 → 成批出图与对账表",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("-c", "--config", required=True, help="设计规格 YAML")
        p.add_argument("--out", help="覆盖输出目录")
        p.add_argument("--variants", type=int, help="覆盖每组变体数量")

    plan_p = sub.add_parser("plan", help="展开任务矩阵并预览提示词，不调用后端")
    common(plan_p)
    plan_p.add_argument("--show", type=int, default=12, help="预览条数，0 表示全部（默认 12）")
    plan_p.add_argument("--prompts", help="把全部提示词导出到文本文件")
    plan_p.add_argument("--json", help="把任务清单导出为 JSON")
    plan_p.set_defaults(func=cmd_plan)

    render_p = sub.add_parser("render", help="批量出图")
    common(render_p)
    render_p.add_argument("--provider", default="ark", help="后端：ark / openai / mock（默认 ark）")
    render_p.add_argument("--model", help="覆盖后端模型名")
    render_p.add_argument("--workers", type=int, default=4, help="并发数（默认 4）")
    render_p.add_argument("--limit", type=int, help="只跑前 N 个任务（试跑用）")
    render_p.add_argument("--retries", type=int, default=2, help="失败重试次数（默认 2）")
    render_p.add_argument("--backoff", type=float, default=2.0, help="重试退避基数秒（默认 2）")
    render_p.add_argument("--force", action="store_true", help="忽略本地已有文件，强制重跑")
    render_p.add_argument("--dry-run", action="store_true", help="只打印将要出图的任务与提示词")
    render_p.set_defaults(func=cmd_render)

    report_p = sub.add_parser("report", help="校验并汇总 manifest")
    report_p.add_argument("--dir", required=True, help="输出目录（含 manifest.csv）")
    report_p.set_defaults(func=cmd_report)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (SpecError, ProviderError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断；已完成的图片与 manifest 不会丢失，重新执行会跳过已出图的任务。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
