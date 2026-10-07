import unittest

from llm_terminal_assistant.tools.errors import ToolLoopStoppedError, ToolLoopStopReason
from llm_terminal_assistant.tools.loop import ToolExecutionBudget


class ToolExecutionBudgetTests(unittest.TestCase):
    def test_exhausted_budget_stops_without_consuming_more(self):
        budget = ToolExecutionBudget(max_tool_executions=2)
        self.assertEqual(budget.used_tool_executions, 0)

        budget.consume()
        budget.consume()
        self.assertEqual(budget.used_tool_executions, 2)

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                with self.assertRaises(ToolLoopStoppedError) as caught:
                    budget.consume()

                self.assertEqual(
                    caught.exception.reason,
                    ToolLoopStopReason.MAX_TOOL_EXECUTIONS_REACHED,
                )
                self.assertEqual(budget.used_tool_executions, 2)


if __name__ == "__main__":
    unittest.main()
