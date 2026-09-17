"""阶段 4：项目类型。

本文件只定义应用内部使用的学习卡片类型化结构，字段与 Schema 契约对应
（标题、摘要、复习问题、来源 ID 等），供业务代码依赖，避免各处直接访问原始字典。

验证流水线的阶段 4（pipeline.py）使用已经通过 Schema 和业务规则校验的数据
构造该类型。类型字段与 Schema 保持一致，因此模型输出造成的字段缺失或类型错误
会在构造前被拒绝。
"""

from dataclasses import dataclass


@dataclass
class StudyCard:
    title: str
    summary: str
    questions: list[str]
    source_ids: list[str]
