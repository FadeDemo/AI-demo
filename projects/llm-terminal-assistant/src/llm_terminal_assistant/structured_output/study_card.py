"""阶段 4：项目类型。

本文件只定义应用内部使用的学习卡片类型化结构，字段与 Schema 契约对应
（标题、摘要、复习问题、来源 ID 等），供业务代码依赖，避免各处直接访问原始字典。

把通过校验的数据值转换为该类型，由验证流水线的阶段 4（pipeline.py）执行；
转换失败类别统一使用 errors.py 中的错误类型。
"""

from dataclasses import dataclass


@dataclass
class StudyCard:
    title: str
    summary: str
    questions: list[str]
    source_ids: list[str]
