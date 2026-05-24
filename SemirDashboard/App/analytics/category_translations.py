"""
App/analytics/category_translations.py
Chinese → Vietnamese translations for category_l1 / category_l2 / category_l3.
Controlled by CATEGORY_LANG setting (default 'VI').
When CATEGORY_LANG == 'VI', display format: "中文 (Tiếng Việt)".
"""

# fmt: off
ZH_TO_VI: dict[str, str] = {
    # ── Category L1 ─────────────────────────────────────────────
    "商品":              "Hàng hóa",
    "促销品":            "Hàng khuyến mãi",
    "手提袋":            "Túi mua sắm",
    "道具":              "Đạo cụ trưng bày",
    "非生产性辅料":       "Phụ liệu",

    # ── Category L2 — T-shirts / Shirts ─────────────────────────
    "POLO衫":            "Áo polo",
    "短袖T恤":           "Áo thun ngắn tay",
    "中袖T恤":           "Áo thun tay lỡ",
    "长袖T恤":           "Áo thun dài tay",
    "短袖衬衫":          "Áo sơ mi ngắn tay",
    "中袖衬衫":          "Áo sơ mi tay lỡ",
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
    "棉服":              "Áo bông",
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
    "围巾":              "Khăn quàng",

    # ── Category L2 — Lifestyle / Other ──────────────────────────
    "日用品":            "Đồ dùng hàng ngày",
    "水杯":              "Bình nước",
    "玩具":              "Đồ chơi",
    "辅料":              "Phụ liệu",

    # ── Category L3 — T-shirts (detail) ─────────────────────────
    "短袖POLO":          "Áo polo ngắn tay",
    "长袖POLO":          "Áo polo dài tay",
    "圆领长袖T恤":       "Áo thun dài tay cổ tròn",
    "中领长袖T恤":       "Áo thun dài tay cổ vừa",
    "圆V领短袖T恤":      "Áo thun ngắn tay cổ tròn/V",
    "圆V领中袖T恤":      "Áo thun tay lỡ cổ tròn/V",
    "圆V领长袖T恤":      "Áo thun dài tay cổ tròn/V",
    "翻领短袖T恤":       "Áo thun ngắn tay cổ bẻ",
    "翻领长袖T恤":       "Áo thun dài tay cổ bẻ",
    "带帽长袖T恤":       "Áo thun dài tay có mũ",
    "其他短袖T恤":       "Áo thun ngắn tay khác",
    "其他长袖T恤":       "Áo thun dài tay khác",

    # ── Category L3 — Shirts (detail) ───────────────────────────
    "净色衬衫":          "Áo sơ mi trơn",
    "印花衬衫":          "Áo sơ mi in họa tiết",
    "梭织短袖衬衫":      "Áo sơ mi ngắn tay dệt thoi",
    "梭织长袖衬衫":      "Áo sơ mi dài tay dệt thoi",
    "牛仔短袖衬衫":      "Áo sơ mi ngắn tay denim",
    "牛仔衬衫":          "Áo sơ mi denim",
    "牛仔长袖衬衫":      "Áo sơ mi dài tay denim",
    "其他长袖衬衫":      "Áo sơ mi dài tay khác",

    # ── Category L3 — Knitwear / Hoodies (detail) ───────────────
    "V领毛衫":           "Áo len cổ V",
    "圆领毛衫":          "Áo len cổ tròn",
    "中领毛衫":          "Áo len cổ vừa",
    "翻领毛衫":          "Áo len cổ bẻ",
    "假两件毛衫":        "Áo len giả hai lớp",
    "毛开衫":            "Áo len cardigan",
    "其他毛衫":          "Áo len khác",
    "圆领卫衣":          "Áo hoodie cổ tròn",
    "中领卫衣":          "Áo hoodie cổ vừa",
    "带帽卫衣":          "Áo hoodie có mũ",
    "连帽卫衣":          "Áo hoodie liền mũ",
    "半开襟卫衣":        "Áo hoodie nửa khóa",
    "假两件卫衣":        "Áo hoodie giả hai lớp",
    "拼接领卫衣":        "Áo hoodie cổ ghép",

    # ── Category L3 — Outerwear (detail) ────────────────────────
    "短羽绒服":          "Áo phao ngắn",
    "中羽绒服":          "Áo phao dài vừa",
    "化纤茄克":          "Áo jacket tổng hợp",
    "牛仔茄克":          "Áo jacket denim",
    "针织茄克":          "Áo jacket dệt kim",
    "其他茄克":          "Áo jacket khác",
    "充棉马甲":          "Áo gile bông",
    "充绒马甲":          "Áo gile lông vũ",
    "梭织马甲":          "Áo gile dệt thoi",
    "牛仔马甲":          "Áo gile denim",
    "毛织马甲":          "Áo gile len đan",
    "梭织棉服":          "Áo bông dệt thoi",

    # ── Category L3 — Vests / Tanks ─────────────────────────────
    "吊带背心":          "Áo hai dây",
    "宽肩背心":          "Áo ba lỗ vai rộng",
    "窄肩背心":          "Áo ba lỗ vai hẹp",
    "内衣背心":          "Áo ba lỗ lót",
    "毛织背心":          "Áo gile len đan",
    "针织背心":          "Áo ba lỗ dệt kim",
    "打底衫":            "Áo mặc trong",

    # ── Category L3 — Underwear (detail) ────────────────────────
    "Bra-in":            "Áo lót Bra-in",
    "净色文胸":          "Áo ngực trơn",
    "圆领内衣":          "Đồ lót cổ tròn",
    "内衣套装":          "Bộ đồ lót",
    "三角裤":            "Quần lót tam giác",
    "三角针织裤":        "Quần lót tam giác dệt kim",
    "平角裤":            "Quần lót boxer",
    "平角针织裤":        "Quần boxer dệt kim",
    "套装内裤":          "Quần lót bộ",

    # ── Category L3 — Loungewear ─────────────────────────────────
    "家居上装":          "Áo mặc nhà",
    "家居套装":          "Bộ đồ mặc nhà",
    "家居裙装":          "Váy mặc nhà",

    # ── Category L3 — Bottoms (detail) ──────────────────────────
    "牛仔中裤":          "Quần jeans lửng",
    "牛仔便服":          "Quần áo casual denim",
    "其他牛仔裤":        "Quần jeans khác",
    "直筒裤":            "Quần ống suôn",
    "锥型裤":            "Quần ống côn",
    "锥形裤":            "Quần ống côn",
    "阔腿裤":            "Quần ống rộng",
    "工装裤":            "Quần cargo",
    "修身小脚裤":        "Quần slim ống nhỏ",
    "合体裤":            "Quần vừa vặn",
    "基本裤":            "Quần cơ bản",
    "梭织长裤":          "Quần dài dệt thoi",
    "梭织中裤":          "Quần lửng dệt thoi",
    "梭织短裤":          "Quần short dệt thoi",
    "梭织慢跑裤":        "Quần jogger dệt thoi",
    "针织长裤":          "Quần dài dệt kim",
    "针织中裤":          "Quần lửng dệt kim",
    "针织短裤":          "Quần short dệt kim",
    "针织慢跑裤":        "Quần jogger dệt kim",
    "打底长裤":          "Quần legging dài",
    "打底七分裤":        "Quần legging 7 tấc",
    "打底五分裤":        "Quần legging 5 tấc",

    # ── Category L3 — Dresses / Skirts / Sets (detail) ──────────
    "A字裙":             "Váy chữ A",
    "百褶裙":            "Váy xếp ly",
    "牛仔短裙":          "Chân váy ngắn denim",
    "梭织短裙":          "Chân váy ngắn dệt thoi",
    "针织短裙":          "Chân váy ngắn dệt kim",
    "牛仔连衣裙":        "Váy liền denim",
    "梭织连衣裙":        "Váy liền dệt thoi",
    "毛织连衣裙":        "Váy liền len đan",
    "针织连衣裙":        "Váy liền dệt kim",
    "套装连衣裙":        "Váy liền bộ",
    "梭织长袖套装":      "Bộ dài tay dệt thoi",
    "毛织长袖套装":      "Bộ dài tay len đan",
    "针织长袖套装":      "Bộ dài tay dệt kim",
    "牛仔长袖套装":      "Bộ dài tay denim",
    "化纤便服":          "Quần áo casual tổng hợp",
    "梭织便服":          "Quần áo casual dệt thoi",
    "针织便服":          "Quần áo casual dệt kim",

    # ── Category L3 — Swimwear (detail) ─────────────────────────
    "分体泳衣":          "Đồ bơi hai mảnh",
    "连体泳衣":          "Đồ bơi liền mảnh",
    "泳裤":              "Quần bơi",
    "泳镜":              "Kính bơi",

    # ── Category L3 — Baby / Kids (detail) ──────────────────────
    "婴童宝宝服礼盒":    "Hộp quà quần áo trẻ em",
    "婴童内着其他连体衣": "Quần áo liền thân trẻ em (mặc trong)",
    "其他连体衣":        "Quần áo liền thân khác",
    "梭织连体衣":        "Quần áo liền thân dệt thoi",
    "针织连体衣":        "Quần áo liền thân dệt kim",

    # ── Category L3 — Footwear (detail) ─────────────────────────
    "人字拖":            "Dép kẹp",
    "休闲拖鞋":          "Dép casual",
    "运动凉鞋":          "Dép thể thao",
    "健步鞋":            "Giày đi bộ",
    "慢跑鞋":            "Giày chạy bộ",
    "板鞋":              "Giày skate",
    "其他运动鞋":        "Giày thể thao khác",

    # ── Category L3 — Socks ──────────────────────────────────────
    "中筒袜":            "Tất cổ vừa",
    "低筒袜":            "Tất cổ thấp",
    "短袜":              "Tất ngắn",
    "地板袜":            "Tất đi nhà",
    "船袜":              "Tất thuyền",
    "浅口隐形袜":        "Tất ẩn mũi cạn",
    "隐形袜":            "Tất ẩn",
    "袖套":              "Tay áo chống nắng",

    # ── Category L3 — Hats ───────────────────────────────────────
    "棒球帽":            "Mũ lưỡi trai",
    "毛线帽":            "Mũ len",
    "盆帽":              "Mũ bucket",
    "空顶帽":            "Mũ không đỉnh",
    "草帽":              "Mũ cói",
    "软沿帽":            "Mũ vành mềm",
    "遮阳帽":            "Mũ che nắng",
    "其他帽子":          "Mũ khác",

    # ── Category L3 — Bags ───────────────────────────────────────
    "书包":              "Balo học sinh",
    "双肩包":            "Balo",
    "单肩包":            "Túi đeo vai",
    "斜挎包":            "Túi đeo chéo",
    "休闲包":            "Túi casual",
    "其他包":            "Túi khác",

    # ── Category L3 — Accessories / Jewellery ────────────────────
    "发夹":              "Kẹp tóc",
    "发箍":              "Băng đô",
    "发绳":              "Dây buộc tóc",
    "啪啪圈":            "Vòng tay snap",
    "戒指":              "Nhẫn",
    "耳夹":              "Kẹp tai",
    "项链":              "Vòng cổ",
    "梭织围巾":          "Khăn quàng dệt thoi",

    # ── Category L3 — Lifestyle / Props / Other ───────────────────
    "冷水杯":            "Bình nước lạnh",
    "毛绒玩具":          "Đồ chơi nhồi bông",
    "魔法棒":            "Gậy phép thuật",
    "常规礼品":          "Quà tặng thông thường",
    "其他促销品/礼品":   "Hàng khuyến mãi / quà tặng khác",
    "压克力套盒":        "Hộp acrylic",
    "纸质套盒":          "Hộp giấy",
    "挂件":              "Đồ treo trang trí",
    "贴纸":              "Nhãn dán",
    "陈列品":            "Hàng trưng bày",
    "其他道具":          "Đạo cụ khác",
    "其他辅料":          "Phụ liệu khác",
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
