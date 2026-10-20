"""Conservative, shared rule evidence for content reviews and offline evaluation.

Matching vocabulary cannot establish factual correctness. These checks expose
detectable conflicts; an empty finding list is not a semantic verification.
"""

import re
from decimal import Decimal

_NUMBER = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*"
    r"(万亿元|亿元|万元|美元|元|个百分点|％|%|公里|分钟|小时|个月|"
    r"个|位|名|人|次|篇|条|项|家|栋|辆|种|份|周|月|日|号|年|岁|吨|班|路|天)"
)
_ENTITY = re.compile(
    r"[一-龥A-Za-z]{2,12}"
    r"(?:大学|学院|医院|公司|集团|政府|委员会|协会|银行|学校|图书馆|博物馆|社区|派出所|车站|机场|公园)"
)
_NEGATION = re.compile(r"没有|禁止|不得|无法|尚未|不|未")
_MONEY = {"元": 1, "万元": 10_000, "亿元": 100_000_000, "万亿元": 1_000_000_000_000}


def number_facts(text: str) -> list[tuple[str, Decimal, str]]:
    facts: list[tuple[str, Decimal, str]] = []
    for match in _NUMBER.finditer(text or ""):
        value, unit = Decimal(match[1]), match[2]
        # Currency and percentage points must not be conflated.
        if unit in _MONEY:
            value *= _MONEY[unit]
            unit = "CNY"
        elif unit == "美元":
            unit = "USD"
        elif unit == "％":
            unit = "%"
        elif unit == "号":
            unit = "日"
        facts.append((unit, value, match[0]))
    return facts


def factual_conflicts(
    source: str, content: str, expected_facts: list[str] | None = None
) -> list[str]:
    """Detect unmatched amounts/dates/counts and simple negation reversals.

    Numeric evidence is grouped by its actual unit. New unverified numeric
    claims also require review, even when the source contains no such unit.
    """
    findings: list[str] = []
    known = number_facts(source)
    known_keys = {(unit, value) for unit, value, _ in known}
    for unit, value, raw in number_facts(content):
        if (unit, value) in known_keys:
            continue
        same_kind = [original for kind, _, original in known if kind == unit]
        if same_kind:
            findings.append(f"数字不一致：{raw}（原文：{'、'.join(same_kind[:4])}）")
        else:
            findings.append(f"数字未在原文得到验证：{raw}")

    for entity in sorted(set(_ENTITY.findall(content or ""))):
        if entity not in (source or ""):
            findings.append(f"实体未在原文出现：{entity}")

    statements = expected_facts or re.split(r"[。！？；\n]", source or "")
    compact_content = re.sub(r"\s+", "", content or "")
    for statement in statements:
        statement = re.sub(r"\s+", "", statement).strip("，,。 ")
        if not statement or not _NEGATION.search(statement):
            continue
        positive = _NEGATION.sub("", statement)
        if positive and positive in compact_content and statement not in compact_content:
            findings.append(f"否定含义被改写：{statement}")
    return list(dict.fromkeys(findings))
