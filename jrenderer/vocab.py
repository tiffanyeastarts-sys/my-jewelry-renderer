"""材质、宝石、视角词表与提示词构建。

所有词表都是可扩展的普通 dict：新增一项即可在整个批量矩阵里生效，
不需要改渲染逻辑。
"""

METALS = {
    "yellow_gold": {
        "zh": "18K 黄金",
        "en": "18K yellow gold",
        "rgb": (214, 169, 74),
    },
    "white_gold": {
        "zh": "18K 白金",
        "en": "18K white gold",
        "rgb": (214, 216, 220),
    },
    "rose_gold": {
        "zh": "18K 玫瑰金",
        "en": "18K rose gold",
        "rgb": (219, 158, 130),
    },
    "platinum": {
        "zh": "PT950 铂金",
        "en": "PT950 platinum",
        "rgb": (200, 202, 206),
    },
    "black_rhodium": {
        "zh": "黑铑电镀",
        "en": "black rhodium plating",
        "rgb": (52, 54, 58),
    },
}

GEMS = {
    "round_brilliant": {
        "zh": "圆形明亮式切工白钻",
        "en": "round brilliant cut white diamond",
        "hint": "57 个刻面、强烈的内部火彩与台面反光",
        "rgb": (238, 244, 250),
    },
    "emerald_cut": {
        "zh": "祖母绿式切工白钻",
        "en": "emerald cut white diamond",
        "hint": "阶梯状大刻面、长方形轮廓、通透的镜面反射",
        "rgb": (236, 242, 248),
    },
    "oval_sapphire": {
        "zh": "椭圆形切割皇家蓝蓝宝石",
        "en": "oval cut royal blue sapphire",
        "hint": "浓郁饱和的皇家蓝、内部隐约的丝状色带",
        "rgb": (26, 58, 156),
    },
    "ruby": {
        "zh": "椭圆形切割鸽血红红宝石",
        "en": "oval cut pigeon blood ruby",
        "hint": "高饱和的鸽血红、明亮的红色荧光感",
        "rgb": (166, 22, 40),
    },
    "emerald": {
        "zh": "祖母绿切割祖母绿宝石",
        "en": "emerald cut green emerald",
        "hint": "半透明的翠绿色、 jardin 内含物特征",
        "rgb": (24, 122, 82),
    },
    "pearl": {
        "zh": "南洋白珠",
        "en": "South Sea white pearl",
        "hint": "圆润的珍珠光泽、柔和的定向高光与伴色",
        "rgb": (247, 243, 236),
    },
    "aquamarine": {
        "zh": "水滴形切割海蓝宝",
        "en": "pear cut aquamarine",
        "hint": "清透的淡蓝色、内部干净的晶体",
        "rgb": (152, 205, 222),
    },
}

ANGLES = {
    "front": {
        "zh": "正面平视",
        "en": "front view, camera level with the piece",
        "layout": "front",
    },
    "top45": {
        "zh": "45 度俯视",
        "en": "45-degree top view",
        "layout": "top45",
    },
    "side": {
        "zh": "侧面 90 度",
        "en": "side profile view, 90 degrees",
        "layout": "side",
    },
    "macro_detail": {
        "zh": "微距细节特写",
        "en": "extreme macro detail shot of the setting and gem facets",
        "layout": "macro",
    },
}

DEFAULT_STYLE = (
    "高端珠宝商业产品摄影，棚拍三点柔光，微距镜头，"
    "浅景深但产品通体清晰，金属与宝石的反射干净、无环境杂物"
)
DEFAULT_BACKGROUND = "无缝浅灰渐变背景，底部有柔和的倒影与接触阴影"
DEFAULT_RATIO = "1:1"
DEFAULT_SIZE = "2048x2048"

REQUIREMENTS = (
    "金属光泽真实、边缘高光连续；宝石有清晰的刻面分界、折射与内部火彩；"
    "产品完整居中、比例准确；画面内不出现文字、Logo、水印、手指或任何工具；"
    "不要在背景添加多余的装饰物"
)


def _gem_block(gem_key: str, extra: dict | None) -> dict:
    base = dict(GEMS[gem_key])
    if extra:
        base.update(extra)
    return base


def build_prompt(piece: dict, metal_key: str, gem: dict, angle_key: str) -> str:
    """把一件单品 × 一种金属 × 一种宝石 × 一个视角拼成一条完整出图提示词。"""
    metal = METALS[metal_key]
    angle = ANGLES[angle_key]
    style = piece.get("style") or DEFAULT_STYLE
    background = piece.get("background") or DEFAULT_BACKGROUND

    gem_desc = f"{gem['zh']}（{gem['en']}）"
    if gem.get("hint"):
        gem_desc += f"，{gem['hint']}"

    parts = [
        f"{style}。",
        f"主体：{piece['description']}；金属部分为 {metal['zh']}（{metal['en']}），"
        f"主石为 {gem_desc}。",
        f"视角：{angle['zh']}（{angle['en']}），产品占画面约 70%。",
        f"背景：{background}。",
        f"画质要求：{REQUIREMENTS}。",
    ]
    if piece.get("extra_prompt"):
        parts.append(str(piece["extra_prompt"]).rstrip("。") + "。")
    return "".join(parts)


def negative_prompt() -> str:
    return "文字、水印、Logo、多只手、畸形指节、多余宝石、扭曲的金属、低分辨率、噪点"
