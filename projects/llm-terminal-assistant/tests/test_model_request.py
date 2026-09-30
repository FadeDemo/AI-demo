import unittest

from llm_terminal_assistant.model import ModelRequest
from llm_terminal_assistant.tools.factory import create_default_tool_registry


class ModelRequestTests(unittest.TestCase):
    def test_tools_default_to_empty_list(self):
        request = ModelRequest(input=[], reserved_output_tokens=128)

        self.assertEqual(request.tools, [])

    def test_accepts_tool_definitions_from_registry(self):
        definitions = create_default_tool_registry().get_tool_list()

        request = ModelRequest(
            input=[],
            reserved_output_tokens=128,
            tools=definitions,
        )

        self.assertEqual(request.tools, definitions)


if __name__ == "__main__":
    unittest.main()
