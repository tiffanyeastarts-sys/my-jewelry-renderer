"""读取设计规格 YAML，并把"单品 × 金属 × 宝石 × 视角 × 变体"展开成出图任务矩阵。"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .vocab import ANGLES, DEFAULT_RATIO, DEFAULT_SIZE, GEMS, METALS, _gem_block, build_prompt


class SpecError(ValueError):
    """设计规格本身不成立（字段缺失、键名拼错等）。"""


@dataclass
class Job:
    index: int
    piece_name: str
    metal_key: str
    gem_key: str
    angle_key: str
    variant: int
    prompt: str
    out_path: Path
    size: str
    ratio: str

    @property
    def metal_label(self) -> str:
        return METALS[self.metal_key]["zh"]

    @property
    def gem_label(self) -> str:
        return GEMS[self.gem_key]["zh"]

    @property
    def angle_label(self) -> str:
        return ANGLES[self.angle_key]["zh"]


@dataclass
class Spec:
    piece: dict
    metals: list
    gem_specs: list
    angles: list
    variants: int
    size: str
    ratio: str
    out_dir: Path
    reference_image: str | None = None
    jobs: list = field(default_factory=list)

    @property
    def piece_name(self) -> str:
        return self.piece["name"]


def _as_list(value, field_name: str) -> list:
    if value is None:
        raise SpecError(f"缺少字段 {field_name}")
    if not isinstance(value, list) or not value:
        raise SpecError(f"{field_name} 必须是非空列表")
    return value


def _gem_from_item(item) -> tuple[str, dict]:
    """宝石可以写成字符串键名，也可以写成带附加属性的 dict。"""
    if isinstance(item, str):
        key, extra = item, None
    elif isinstance(item, dict):
        key = item.get("key")
        extra = {k: v for k, v in item.items() if k != "key"} or None
    else:
        raise SpecError(f"无法识别的宝石项：{item!r}")

    if key not in GEMS:
        raise SpecError(f"未知宝石键 {key!r}，可用：{', '.join(GEMS)}")
    return key, _gem_block(key, extra)


def _check_keys(items, table, field_name: str) -> None:
    for item in items:
        key = item if isinstance(item, str) else item.get("key")
        if key not in table:
            raise SpecError(f"{field_name} 中的 {key!r} 不在词表内，可用：{', '.join(table)}")


def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in str(text)]
    return "".join(keep).strip("-") or "piece"


def load_spec(config_path: str | Path, out_dir: str | Path | None = None, variants: int | None = None) -> Spec:
    config_path = Path(config_path)
    if not config_path.exists():
        raise SpecError(f"配置文件不存在：{config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    piece = raw.get("piece") or {}
    if not piece.get("name"):
        raise SpecError("piece.name 必填")

    metals = _as_list(raw.get("metals"), "metals")
    _check_keys(metals, METALS, "metals")

    gems = _as_list(raw.get("gems"), "gems")
    gem_specs = [_gem_from_item(g) for g in gems]

    angles = _as_list(raw.get("angles"), "angles")
    _check_keys(angles, ANGLES, "angles")

    variants_total = variants if variants is not None else int(raw.get("variants_per_combo", 1))
    if variants_total < 1:
        raise SpecError("variants_per_combo 至少为 1")

    size = str(raw.get("size") or DEFAULT_SIZE)
    ratio = str(raw.get("ratio") or DEFAULT_RATIO)
    reference = raw.get("reference_image")
    if reference == "":
        reference = None

    base_out = Path(out_dir) if out_dir else Path(raw.get("out_dir") or "output")
    base_out = base_out / _slug(piece["name"])

    spec = Spec(
        piece=piece,
        metals=metals,
        gem_specs=gem_specs,
        angles=angles,
        variants=variants_total,
        size=size,
        ratio=ratio,
        out_dir=base_out,
        reference_image=reference,
    )
    spec.jobs = expand(spec)
    return spec


def expand(spec: Spec) -> list:
    """笛卡尔积展开，索引稳定（同配置同顺序 → 同编号，便于断点续跑）。"""
    jobs = []
    idx = 0
    piece_slug = _slug(spec.piece_name)

    for metal_key in spec.metals:
        for gem_key, gem in spec.gem_specs:
            for angle_key in spec.angles:
                for variant in range(1, spec.variants + 1):
                    idx += 1
                    name = f"{piece_slug}__{metal_key}__{gem_key}__{angle_key}__v{variant}.png"
                    jobs.append(
                        Job(
                            index=idx,
                            piece_name=spec.piece_name,
                            metal_key=metal_key,
                            gem_key=gem_key,
                            angle_key=angle_key,
                            variant=variant,
                            prompt=build_prompt(spec.piece, metal_key, gem, angle_key),
                            out_path=spec.out_dir / name,
                            size=spec.size,
                            ratio=spec.ratio,
                        )
                    )
    return jobs
