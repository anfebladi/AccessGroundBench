import unittest
from unittest import mock
import importlib

import vlm_evaluator


class VlmEvaluatorEnvTests(unittest.TestCase):
    @mock.patch("dotenv.load_dotenv")
    def test_import_loads_dotenv(self, load_dotenv_mock):
        importlib.reload(vlm_evaluator)

        load_dotenv_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
