import ast
import os
import unittest


class TestModelConfigStatic(unittest.TestCase):
    def setUp(self):
        self.config_path = os.path.join(os.getcwd(), "orchestrator/config/models.py")

    def test_verify_constants_exist(self):
        """Parse models.py and verify constants are defined correctly."""
        with open(self.config_path) as f:
            tree = ast.parse(f.read())

        constants = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if isinstance(node.value, ast.Constant):
                            constants[target.id] = node.value.value
                        elif isinstance(node.value, ast.Name):  # e.g. DEFAULT = SONNET
                            constants[target.id] = node.value.id

        # Verify 2026 Defaults
        self.assertEqual(constants.get("CLAUDE_SONNET"), "claude-4-5-sonnet")
        self.assertEqual(constants.get("DEFAULT_CLAUDE_MODEL"), "CLAUDE_SONNET")

        self.assertEqual(constants.get("GEMINI_PRO"), "gemini-3-pro")
        self.assertEqual(constants.get("DEFAULT_ARCHITECT_MODEL"), "GEMINI_PRO")

        self.assertEqual(constants.get("CURSOR_CODEX"), "gpt-5.2-codex")
        self.assertEqual(constants.get("DEFAULT_CURSOR_MODEL"), "CURSOR_CODEX")


if __name__ == "__main__":
    unittest.main()
