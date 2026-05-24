"""
App/analytics/category_translations.py
Chinese → Vietnamese translations for SaleDetail category_l1 / category_l2.
Controlled by CATEGORY_LANG setting (default 'VI').
When CATEGORY_LANG == 'VI', display format: "中文 (Tiếng Việt)".
"""

# fmt: off
ZH_TO_VI: dict[str, str] = {
    # ── Category L1 ─────────────────────────────────────────────
    "商品":              "Hàng hóa",
    "促销品":            "Hàng khuyến mãi",
    "手提袋":            "Túi mua sắm",
    "非生产性辅料":       "Phụ liệu",

    # ── Category L2 — T-shirts / Shirts ─────────────────────────
    "POLO衫":            "Áo polo",
    "短袖T恤":           "Áo thun ngắn tay",
    "中袖T恤":           "Áo thun tay lỡ",
    "长袖T恤":           "Áo thun dài tay",
    "短袖衬衫":          "Áo sơ mi ngắn tay",
    "长袖衬衫":          "Áo sơ mi dài tay",

    # ── Category L2 — Knitwear / Sweatshirts ────────────────────
    "套头毛衫":          "Áo len chui đầu",
    "开衫毛衫":          "Áo len cardigan",
    "开襟毛衫":          "Áo len cardigan",
    "毛衫":              "Áo len",
    "卫衣":              "Áo hoodie",
    "长袖卫衣":          "Áo hoodie dài tay",

    # ── Category L2 — Outerwear ─────────────────────────────────
    "茄克":              "Áo jacket",
    "马甲":              "Áo gile",
    "羽绒服":            "Áo phao",
    "背心":              "Áo ba lỗ",

    # ── Category L2 — Underwear / Loungewear ────────────────────
    "文胸":              "Áo lót (bra)",
    "胸衣":              "Áo ngực",
    "内衣":              "Đồ lót",
    "内裤":              "Quần lót",
    "短款内裤":          "Quần lót ngắn",
    "家居服":            "Đồ mặc nhà",
    "家居":              "Đồ gia dụng",

    # ── Category L2 — Bottoms ───────────────────────────────────
    "牛仔长裤":          "Quần jeans dài",
    "牛仔短裤":          "Quần jeans ngắn",
    "长裤":              "Quần dài",
    "中裤":              "Quần lửng",
    "短裤":              "Quần short",
    "休闲长裤":          "Quần dài casual",
    "休闲中裤":          "Quần lửng casual",
    "休闲短裤":          "Quần short casual",
    "打底裤":            "Quần legging",

    # ── Category L2 — Dresses / Skirts / Sets ───────────────────
    "连衣裙":            "Váy liền",
    "半裙":              "Chân váy",
    "短裙":              "Chân váy ngắn",
    "套装":              "Bộ trang phục",
    "长袖套装":          "Bộ dài tay",
    "便服":              "Trang phục thường ngày",

    # ── Category L2 — Swimwear ───────────────────────────────────
    "泳衣":              "Đồ bơi",

    # ── Category L2 — Baby / Kids ────────────────────────────────
    "婴童外出连体衣":    "Quần áo liền thân trẻ em (ra ngoài)",
    "婴童内着连体衣":    "Quần áo liền thân trẻ em (mặc trong)",
    "婴童三角衣":        "Quần tam giác trẻ sơ sinh",
    "婴童礼盒":          "Hộp quà trẻ em",

    # ── Category L2 — Footwear ───────────────────────────────────
    "休闲鞋":            "Giày thể thao casual",
    "运动鞋":            "Giày thể thao",
    "凉鞋":              "Dép xăng đan",
    "拖鞋":              "Dép lào",

    # ── Category L2 — Accessories ────────────────────────────────
    "袜子":              "Tất",
    "帽子":              "Mũ",
    "眼镜":              "Kính mắt",
    "饰品":              "Phụ kiện",
    "包":                "Túi xách",

    # ── Category L2 — Lifestyle / Other ──────────────────────────
    "日用品":            "Đồ dùng hàng ngày",
    "水杯":              "Bình nước",
    "玩具":              "Đồ chơi",
    "促销品":            "Hàng khuyến mãi",
    "手提袋":            "Túi mua sắm",
    "辅料":              "Phụ liệu",
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
