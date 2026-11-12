import os
import unittest
from unittest.mock import patch

from git_dashboard.services.folders import WindowsFolderDialog


@unittest.skipUnless(os.name == "nt", "Windows Common Item Dialog")
class FolderTests(unittest.TestCase):
    def test_native_dialog_initializes_without_tk_and_cancel_is_not_an_error(self):
        with WindowsFolderDialog() as dialog:
            self.assertTrue(dialog.options & 0x20)
            self.assertTrue(dialog.options & 0x40)
            with patch.object(dialog, "_show", return_value=-2147023673):
                self.assertEqual(dialog.select(), "")
        self.assertFalse(dialog.pointer)
