from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Draft:
    draft_id: str
    content: str


class IdempotencyConflictError(ValueError):
    pass


@dataclass
class InMemoryDraftStore:
    drafts: dict[str, Draft] = field(default_factory=dict)

    def create_draft(self, idempotency_key: str, content: str) -> Draft:
        if content is None or content == "":
            raise ValueError("Content cannot be None or empty")
        if idempotency_key in self.drafts:
            if self.drafts[idempotency_key].content == content:
                return self.drafts[idempotency_key]
            else:
                raise IdempotencyConflictError(
                    f"Idempotency key {idempotency_key} already exists with different content"
                )
        draft_id = uuid4().hex
        draft = Draft(draft_id=draft_id, content=content)
        self.drafts[idempotency_key] = draft
        return draft
