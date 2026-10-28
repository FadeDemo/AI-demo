import unittest

from llm_terminal_assistant.draft_store import InMemoryDraftStore


class InMemoryDraftStoreTests(unittest.TestCase):
    def test_creates_and_stores_draft_without_changing_content(self):
        store = InMemoryDraftStore()
        content = "  First line\nSecond line  "

        draft = store.create_draft(content)

        self.assertTrue(draft.draft_id)
        self.assertEqual(draft.content, content)
        self.assertEqual(store.drafts, {draft.draft_id: draft})

    def test_empty_content_is_rejected_without_changing_saved_drafts(self):
        store = InMemoryDraftStore()
        draft = store.create_draft("Existing draft")

        with self.assertRaises(ValueError):
            store.create_draft("")

        self.assertEqual(store.drafts, {draft.draft_id: draft})
        self.assertEqual(draft.content, "Existing draft")

    def test_store_instances_keep_separate_records(self):
        first_store = InMemoryDraftStore()
        second_store = InMemoryDraftStore()
        self.assertEqual(first_store.drafts, {})
        self.assertEqual(second_store.drafts, {})

        first_draft = first_store.create_draft("First store draft")

        self.assertEqual(second_store.drafts, {})

        second_draft = second_store.create_draft("Second store draft")

        self.assertEqual(first_store.drafts, {first_draft.draft_id: first_draft})
        self.assertEqual(second_store.drafts, {second_draft.draft_id: second_draft})


if __name__ == "__main__":
    unittest.main()
