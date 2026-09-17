"""When the chat widget makes a sound, and when it stays quiet.

This is behaviour no Python test can reach and no amount of reading can settle:
the rule is "ring for a message the visitor did not cause and is not already
looking at", and every clause of that has an off-by-one waiting in it. Ring on
first load and every page navigation chimes. Ring on the answer to their own
message and it pings at them for the reply they are reading. Ring never, which
is where it started, and a reply to somebody who switched tabs arrives in
silence.

So the real widget is rendered, its script lifted out of the page, and driven
under stubs by Node. Nothing is duplicated -- a change to the widget is a change
to what this runs.

Skipped where Node is not installed, which includes the deploy host. The test is
for the machine the change is made on.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

HARNESS = Path(__file__).parent / "jstests" / "chime_harness.js"
User = get_user_model()


class WidgetChimeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # The widget only renders for a signed-in visitor; the assistant costs
        # money per message, so it is behind the login rather than behind being
        # hidden.
        cls.customer = User.objects.create_user(
            email="chatter@example.com", password="x", email_verified=True)

    def test_the_chime_fires_only_when_it_should(self):
        node = shutil.which("node") or shutil.which("nodejs")
        if node is None:
            self.skipTest("node is not installed here")

        self.client.force_login(self.customer)
        page = self.client.get(reverse("home")).content.decode()
        match = re.search(r"<script>\s*\(function \(\) \{\s*var API = \"[^\"]*assistant",
                          page)
        self.assertIsNotNone(match, "the widget script is not on the page any more")
        start = page.index("<script>", match.start()) + len("<script>")
        script = page[start:page.index("</script>", start)]

        with tempfile.TemporaryDirectory() as tmp:
            widget = Path(tmp) / "widget.js"
            widget.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [node, str(HARNESS), str(widget)],
                capture_output=True, text=True, timeout=60,
            )
        # The harness prints one line per rule, so a failure names the rule that
        # broke rather than just the count.
        self.assertEqual(result.returncode, 0,
                         f"\n{result.stdout}\n{result.stderr}")
        self.assertIn("passed", result.stdout)
