import unittest
from unittest.mock import call, patch

from llm_terminal_assistant.draft_store import (
    Draft,
    IdempotencyConflictError,
    InMemoryDraftStore,
)


class LoseFirstResponseTransport:
    def __init__(self, store: InMemoryDraftStore):
        self.store = store
        self.response_lost = False

    def create_draft(self, idempotency_key: str, content: str) -> Draft:
        draft = self.store.create_draft(idempotency_key, content)
        if not self.response_lost:
            self.response_lost = True
            raise TimeoutError("Simulated response loss after draft creation.")
        return draft


class InMemoryDraftStoreTests(unittest.TestCase):
    def test_creates_and_stores_draft_without_changing_content(self):
        store = InMemoryDraftStore()
        content = "  First line\nSecond line  "

        draft = store.create_draft("operation-1", content)

        self.assertTrue(draft.draft_id)
        self.assertEqual(draft.content, content)
        self.assertEqual(store.drafts, {"operation-1": draft})

    def test_empty_content_is_rejected_without_changing_saved_drafts(self):
        store = InMemoryDraftStore()
        draft = store.create_draft("operation-1", "Existing draft")

        with patch(
            "llm_terminal_assistant.draft_store.Draft", wraps=Draft
        ) as draft_factory:
            for key in ("operation-1", "operation-2"):
                with self.subTest(key=key):
                    with self.assertRaises(ValueError) as raised:
                        store.create_draft(key, "")
                    self.assertNotIsInstance(raised.exception, IdempotencyConflictError)

        draft_factory.assert_not_called()
        self.assertEqual(store.drafts, {"operation-1": draft})
        self.assertEqual(draft.content, "Existing draft")

    def test_same_key_and_content_replay_returns_saved_draft_without_creating_one(self):
        store = InMemoryDraftStore()
        content = "Same draft content"

        with patch(
            "llm_terminal_assistant.draft_store.Draft", wraps=Draft
        ) as draft_factory:
            original = store.create_draft("operation-1", content)
            original_id = original.draft_id
            replayed = store.create_draft("operation-1", content)

        self.assertEqual(draft_factory.call_count, 1)
        self.assertEqual(replayed, original)
        self.assertEqual(replayed.draft_id, original_id)
        self.assertEqual(replayed.content, content)
        self.assertEqual(store.drafts, {"operation-1": original})

    def test_replay_after_lost_response_reaches_store_twice_and_creates_one_draft(self):
        store = InMemoryDraftStore()
        transport = LoseFirstResponseTransport(store)
        idempotency_key = "operation-1"
        content = "  Draft whose first response is lost\n"

        with (
            patch(
                "llm_terminal_assistant.draft_store.Draft", wraps=Draft
            ) as draft_factory,
            patch.object(
                store, "create_draft", wraps=store.create_draft
            ) as store_create_draft,
        ):
            with self.assertRaises(TimeoutError):
                transport.create_draft(idempotency_key, content)

            store_create_draft.assert_called_once_with(idempotency_key, content)
            self.assertEqual(draft_factory.call_count, 1)
            self.assertEqual(len(store.drafts), 1)
            saved = store.drafts[idempotency_key]
            saved_id = saved.draft_id
            self.assertTrue(saved_id)
            self.assertEqual(saved.content, content)

            replayed = transport.create_draft(idempotency_key, content)

        self.assertEqual(
            store_create_draft.call_args_list,
            [call(idempotency_key, content), call(idempotency_key, content)],
        )
        self.assertEqual(draft_factory.call_count, 1)
        self.assertEqual(store.drafts, {idempotency_key: saved})
        self.assertEqual(replayed, saved)
        self.assertEqual(replayed.draft_id, saved_id)
        self.assertEqual(replayed.content, content)

    def test_same_key_with_different_content_conflicts_without_changing_saved_draft(
        self,
    ):
        store = InMemoryDraftStore()

        with patch(
            "llm_terminal_assistant.draft_store.Draft", wraps=Draft
        ) as draft_factory:
            original = store.create_draft("operation-1", "Original content")
            original_id = original.draft_id

            with self.assertRaises(IdempotencyConflictError):
                store.create_draft("operation-1", "Different content")

        self.assertEqual(draft_factory.call_count, 1)
        self.assertEqual(store.drafts, {"operation-1": original})
        self.assertEqual(original.draft_id, original_id)
        self.assertEqual(original.content, "Original content")

    def test_new_key_creates_another_draft_even_when_content_is_identical(self):
        store = InMemoryDraftStore()
        content = "Same draft content"

        with patch(
            "llm_terminal_assistant.draft_store.Draft", wraps=Draft
        ) as draft_factory:
            first = store.create_draft("operation-1", content)
            second = store.create_draft("operation-2", content)

        self.assertEqual(draft_factory.call_count, 2)
        self.assertNotEqual(first.draft_id, second.draft_id)
        self.assertEqual(first.content, content)
        self.assertEqual(second.content, content)
        self.assertEqual(store.drafts, {"operation-1": first, "operation-2": second})

    def test_store_instances_keep_separate_records(self):
        first_store = InMemoryDraftStore()
        second_store = InMemoryDraftStore()
        self.assertEqual(first_store.drafts, {})
        self.assertEqual(second_store.drafts, {})

        first_draft = first_store.create_draft("operation-1", "First store draft")

        self.assertEqual(second_store.drafts, {})

        second_draft = second_store.create_draft("operation-1", "Second store draft")

        self.assertEqual(first_store.drafts, {"operation-1": first_draft})
        self.assertEqual(second_store.drafts, {"operation-1": second_draft})


if __name__ == "__main__":
    unittest.main()
