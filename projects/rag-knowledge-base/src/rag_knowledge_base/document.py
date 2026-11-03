"""任务 1 的文档记录类型在本模块中定义。"""

from dataclasses import dataclass


@dataclass
class Document:
    doc_id: str
    title: str
    text: str
    source: str
