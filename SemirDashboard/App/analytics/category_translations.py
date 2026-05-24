"""
App/analytics/category_translations.py
Chinese → Vietnamese translations for SaleDetail category_l1 / category_l2.
Controlled by CATEGORY_LANG setting (default 'VI').
When CATEGORY_LANG == 'VI', display format: "中文 (Tiếng Việt)".
"""

# fmt: off
ZH_TO_VI: dict[str, str] = {
    # ── Category L1 ─────────────────────────────────────────────
    "商品":          "Hàng hóa",
    "促销品":        "Hàng khuyến mãi",
    "手提袋":        "Túi mua sắm",
    "非生产性辅料":   "Phụ liệu",

    # ── Category L2 — Tops ──────────────────────────────────────
    "POLO衫":        "Áo polo",
    "短袖T恤":       "Áo thun ngắn tay",
    "长袖T恤":       "Áo thun dài tay",
    "短袖衬衫":      "Áo sơ mi ngắn tay",
    "长袖衬衫":      "Áo sơ mi dài tay",
    "文胸":          "Áo lót (bra)",
    "内衣":          "Đồ lót",

    # ── Category L2 — Knitwear ──────────────────────────────────
    "套头毛衫":      "Áo len chui đầu",
    "开衫毛衫":      "Áo len cardigan",
    "毛衫":          "Áo len",

    # ── Category L2 — Outerwear ─────────────────────────────────
    "茄克":          "Áo jacket",
    "背心":          "Áo vest / ba lỗ",

    # ── Category L2 — Bottoms ───────────────────────────────────
    "牛仔长裤":      "Quần jeans dài",
    "牛仔短裤":      "Quần jeans ngắn",
    "休闲短裤":      "Quần short casual",
    "短款内裤":      "Quần lót ngắn",
    "休闲长裤":      "Quần dài casual",

    # ── Category L2 — Dresses / Sets ────────────────────────────
    "连衣裙":        "Váy liền",
    "半裙":          "Chân váy",
    "套装":          "Bộ (set)",
    "长袖套装":      "Bộ dài tay",
    "家居服":        "Đồ mặc nhà",

    # ── Category L2 — Footwear / Accessories ────────────────────
    "拖鞋":          "Dép lào",
    "休闲鞋":        "Giày thể thao casual",
    "袜子":          "Tất",
    "包":            "Túi xách",

    # ── Category L2 — Other ─────────────────────────────────────
    "促销品":        "Hàng khuyến mãi",
    "手提袋":        "Túi mua sắm",
    "辅料":          "Phụ liệu",
}
# fmt: on


def translate_category(zh_text: str, lang: str = "VI") -> str:
    """
    Return display string for a category value.
    lang='VI': "中文 (Tiếng Việt)" if translation exists, else original.
    lang='ZH': original Chinese only.
    """
    if not zh_text:
        return zh_text or "—"
    if lang.upper() != "VI":
        return zh_text
    vi = ZH_TO_VI.get(zh_text)
    if vi:
        return f"{zh_text} ({vi})"
    return zh_text
