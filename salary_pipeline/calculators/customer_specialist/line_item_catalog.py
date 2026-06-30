"""客户专员左侧行项目录 — 与「客户部提成」A–H 列对齐。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineItemSpec:
    id: str
    label: str
    category: str  # 必做 | 机动 | 增值
    excel_row: int


@dataclass(frozen=True)
class LineItemSection:
    id: str
    label: str
    items: tuple[LineItemSpec, ...]


LINE_ITEM_SECTIONS: tuple[LineItemSection, ...] = (
    LineItemSection(
        id="bizuo",
        label="必做",
        items=(
            LineItemSpec("3dc_yiwang", "3DC一网", "必做", 4),
            LineItemSpec("3dc_erwang", "3DC二网", "必做", 5),
            LineItemSpec("xinche_5dc", "新车5DC回访", "必做", 6),
            LineItemSpec("xinche_30dc", "新车30DC回访", "必做", 7),
            LineItemSpec("zhanbai_huifang", "战败回访", "必做", 8),
            LineItemSpec("qianke_huifang", "潜客回访", "必做", 9),
            LineItemSpec("xinche_mianfang", "新车面访", "必做", 11),
            LineItemSpec("weixin_weixi", "微信维系", "必做", 12),
            LineItemSpec("tousu_chuli", "投诉处理", "必做", 13),
            LineItemSpec("weixin_tianjia", "微信添加", "必做", 14),
        ),
    ),
    LineItemSection(
        id="jidong",
        label="机动",
        items=(
            LineItemSpec("qita_huifang", "其他回访", "机动", 10),
            LineItemSpec("manyidu", "满意度", "机动", 15),
        ),
    ),
    LineItemSection(
        id="zengzhi",
        label="增值",
        items=(
            LineItemSpec("koubei", "口碑", "增值", 16),
            LineItemSpec("fatie", "发帖", "增值", 17),
            LineItemSpec("n3_shoubao", "N-3首保", "增值", 18),
            LineItemSpec("n4_shoubao", "N-4首保", "增值", 19),
            LineItemSpec("n5_shoubao", "N-5首保", "增值", 20),
            LineItemSpec("n6_erbao", "N-6二保", "增值", 21),
            LineItemSpec("n9_erbao", "N-9二保", "增值", 22),
            LineItemSpec("n12_erbao", "N-12二保", "增值", 23),
            LineItemSpec("n6_dingbao", "N-6定保", "增值", 24),
            LineItemSpec("n9_dingbao", "N-9定保", "增值", 25),
            LineItemSpec("n12_dingbao", "N-12定保", "增值", 26),
            LineItemSpec("waituo", "外拓", "增值", 27),
            LineItemSpec("n6_qita", "N-6其他", "增值", 28),
            LineItemSpec("n9_qita", "N-9其他", "增值", 29),
            LineItemSpec("n12_qita", "N-12其他", "增值", 30),
            LineItemSpec("wufudai", "无福袋", "增值", 31),
            LineItemSpec("chundian_huizhan", "纯电回站", "增值", 32),
            LineItemSpec("cheji", "车机", "增值", 33),
            LineItemSpec("fudai", "福袋", "增值", 34),
            LineItemSpec("zhibao", "质保", "增值", 35),
            LineItemSpec("liushi", "流失", "增值", 36),
            LineItemSpec("xubao", "续保", "增值", 37),
            LineItemSpec("luntai", "轮胎", "增值", 38),
            LineItemSpec("led", "LED", "增值", 39),
            LineItemSpec("mangqu", "盲区", "增值", 40),
            LineItemSpec("xingrui_weideng", "星瑞贯穿尾灯", "增值", 41),
        ),
    ),
)

ALL_LINE_ITEMS: tuple[LineItemSpec, ...] = tuple(
    item for section in LINE_ITEM_SECTIONS for item in section.items
)

LINE_ITEM_BY_ID = {spec.id: spec for spec in ALL_LINE_ITEMS}
LINE_ITEM_BY_LABEL = {spec.label: spec for spec in ALL_LINE_ITEMS}

LEFT_LINE_TEMPLATES = ("left_line_items", "left_and_baoke")
