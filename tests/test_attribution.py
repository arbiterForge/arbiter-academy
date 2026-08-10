from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from academy_engine.command import GitCommandError


class AttributionTests(TestCase):
    def test_display_name_preserves_exact_valid_unicode_value(self) -> None:
        from academy_engine.attribution import validate_display_name

        value = "Ada Lovelace_2-\u00e9\u0661.O'Neil"
        self.assertIs(validate_display_name(value), value)

    def test_display_name_allows_eighty_scalars_and_rejects_unsafe_grammar(self) -> None:
        from academy_engine.attribution import AttributionError, validate_display_name

        self.assertEqual(validate_display_name("A" * 80), "A" * 80)
        for value in (
            "A" * 81, " Ada", "Ada ", "-Ada", "Ada-", "Ada\nName", "Ada/Name",
            "Ada\u2019Name", "e\u0301", "Ada\ud800", "Ada\U0001f600", "Ada\u202eName",
        ):
            with self.subTest(value=repr(value)):
                with self.assertRaises(AttributionError):
                    validate_display_name(value)

    def test_prospective_author_never_discloses_email_or_raw_git_output(self) -> None:
        from academy_engine.attribution import AttributionError, prospective_author_name

        private = "p03-private-canary@example.invalid"
        with patch("academy_engine.attribution.run_git", return_value=SimpleNamespace(stdout=f"Bad/Name <{private}> 1 +0000\n")):
            with self.assertRaises(AttributionError) as caught:
                prospective_author_name(Path("."), trust_local_config=True)
        self.assertEqual(str(caught.exception), "P03 preparation requires a display-safe Git author name.")
        self.assertNotIn(private, str(caught.exception))

    def test_commit_author_requires_exact_nul_and_uses_non_mailmapped_author_format(self) -> None:
        from academy_engine.attribution import AttributionError, commit_author_name

        with patch("academy_engine.attribution.run_git", return_value=SimpleNamespace(stdout="Ada\x00\n")) as run:
            self.assertEqual(commit_author_name(Path("."), "a" * 40), "Ada")
        self.assertEqual(run.call_args.args[1], ["show", "-s", "--format=%an%x00", "a" * 40])
        self.assertNotIn("validate_local_config", run.call_args.kwargs)
        for output in ("Ada\n", "Ada\x00\x00\n", "Ada\x00junk\n", "Ada\x00\r\n"):
            with self.subTest(output=repr(output)), patch("academy_engine.attribution.run_git", return_value=SimpleNamespace(stdout=output)):
                with self.assertRaises(AttributionError):
                    commit_author_name(Path("."), "a" * 40)
        with patch("academy_engine.attribution.run_git", side_effect=GitCommandError("p03-private-canary@example.invalid")):
            with self.assertRaises(AttributionError) as caught:
                commit_author_name(Path("."), "b" * 40)
        self.assertNotIn("p03-private-canary@example.invalid", str(caught.exception))
