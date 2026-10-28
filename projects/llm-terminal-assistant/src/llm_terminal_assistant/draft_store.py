from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Draft:
    draft_id: str
    content: str


@dataclass
class InMemoryDraftStore:
    drafts: dict[str, Draft] = field(default_factory=dict)

    def create_draft(self, content: str) -> Draft:
        if content is None or content == "":
            raise ValueError("Content cannot be None or empty")
        draft_id = uuid4().hex
        draft = Draft(draft_id=draft_id, content=content)
        self.drafts[draft_id] = draft
        return draft
