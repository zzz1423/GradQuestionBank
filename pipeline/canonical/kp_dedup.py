"""
Knowledge Point Deduplication via LLM.

Sends batches of KP names to the LLM and asks it to identify
groups of duplicates or near-duplicates. Returns suggestions
for human review before updating the alias mapping.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pipeline.llm.llm_client import LLMClient, LLMConfig

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一个考研知识点规范化专家。你的任务是找出一组知识点名称中的重复项和近义项。

规则：
1. 只合并真正指向同一概念的知识点（如"函数极限"和"极限"在考研数学中通常指同一知识点）
2. 不要合并范围不同的知识点（如"极限"和"极限的定义"，后者更具体）
3. 每组选择最规范、最常见的名称作为标准名
4. 返回 JSON 数组，每个元素是一组重复项

输出格式（严格 JSON，不要其他文字）：
[
  {
    "canonical": "标准名称",
    "duplicates": ["别名1", "别名2", ...],
    "reason": "简短说明为什么这些是同一概念"
  }
]

如果没有发现重复项，返回空数组 []。"""

_USER_TEMPLATE = """以下是"{subject}"学科下的所有知识点名称：
{kp_list}

请找出其中的重复项和近义项，返回 JSON 数组。"""


class KPDeduplicator:
    """Detect duplicate knowledge points using LLM."""

    def __init__(self, llm_config: LLMConfig | None = None):
        self.llm = LLMClient(llm_config or LLMConfig())

    def find_duplicates(
        self, kps_by_subject: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        """Find duplicate KPs across all subjects.

        Args:
            kps_by_subject: {subject_name: [kp_name, ...]}

        Returns:
            List of duplicate groups, each with canonical, duplicates, reason.
        """
        all_groups: list[dict[str, Any]] = []

        for subject, kp_names in kps_by_subject.items():
            if len(kp_names) < 2:
                continue
            logger.info(f"Analyzing {subject}: {len(kp_names)} KPs")
            groups = self._analyze_subject(subject, kp_names)
            all_groups.extend(groups)

        logger.info(f"Found {len(all_groups)} duplicate groups total")
        return all_groups

    def _analyze_subject(
        self, subject: str, kp_names: list[str]
    ) -> list[dict[str, Any]]:
        """Analyze one subject's KPs for duplicates."""
        # Split into batches if too many KPs
        batch_size = 80
        batches = [
            kp_names[i : i + batch_size]
            for i in range(0, len(kp_names), batch_size)
        ]

        all_groups: list[dict[str, Any]] = []

        for batch in batches:
            kp_list = "\n".join(f"- {name}" for name in batch)
            user_msg = _USER_TEMPLATE.format(subject=subject, kp_list=kp_list)

            try:
                resp = self.llm.chat(
                    system=_SYSTEM_PROMPT,
                    user=user_msg,
                    temperature=0.1,
                    max_tokens=4000,
                )
                groups = self._parse_response(resp.content)
                # Add subject context
                for g in groups:
                    g["subject"] = subject
                all_groups.extend(groups)
            except Exception as e:
                logger.error(f"LLM dedup failed for {subject}: {e}")

        return all_groups

    def _parse_response(self, content: str) -> list[dict[str, Any]]:
        """Parse LLM response into duplicate groups."""
        # Strip markdown code fences
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            result = json.loads(text)
            if isinstance(result, list):
                return [
                    {
                        "canonical": g.get("canonical", "").strip(),
                        "duplicates": [
                            d.strip()
                            for d in g.get("duplicates", [])
                            if d.strip()
                        ],
                        "reason": g.get("reason", ""),
                    }
                    for g in result
                    if g.get("canonical") and g.get("duplicates")
                ]
        except json.JSONDecodeError:
            # Try to find JSON array in the response
            import re
            match = re.search(r"\[[\s\S]*\]", text)
            if match:
                try:
                    result = json.loads(match.group())
                    if isinstance(result, list):
                        return [
                            {
                                "canonical": g.get("canonical", "").strip(),
                                "duplicates": [
                                    d.strip()
                                    for d in g.get("duplicates", [])
                                    if d.strip()
                                ],
                                "reason": g.get("reason", ""),
                            }
                            for g in result
                            if g.get("canonical") and g.get("duplicates")
                        ]
                except json.JSONDecodeError:
                    pass

        logger.warning("Failed to parse LLM dedup response")
        return []
