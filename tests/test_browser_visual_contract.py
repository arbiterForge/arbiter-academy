"""Static contract for Academy's deterministic browser visual regression gate."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_WORKFLOW = ROOT / ".github" / "workflows" / "academy-verify.yml"


def workflow_job(workflow: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        workflow,
    )
    if match is None:
        raise AssertionError(f"missing {name} job")
    return match.group(0)


class BrowserVisualContractTests(unittest.TestCase):
    def test_visual_gate_has_an_exact_dev_dependency_and_committed_baselines(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))

        self.assertTrue(package["private"])
        self.assertEqual(package["devDependencies"], {"@playwright/test": "1.62.1"})
        self.assertEqual(lock["lockfileVersion"], 3)
        self.assertEqual(
            lock["packages"][""]["devDependencies"],
            {"@playwright/test": "1.62.1"},
        )
        self.assertTrue((ROOT / "playwright.config.mjs").is_file())
        self.assertTrue((ROOT / "tests" / "site" / "static-server.mjs").is_file())
        self.assertTrue((ROOT / "tests" / "site" / "visual.spec.mjs").is_file())

        manifest = json.loads(
            (ROOT / "tests" / "site" / "visual-baselines.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["renderer"],
            {
                "playwright": "1.62.1",
                "browser": "chromium-headless-shell-1234",
                "platform": "linux",
                "color_scheme": "dark",
                "locale": "en-US",
                "timezone": "UTC",
                "reduced_motion": "reduce",
            },
        )
        self.assertEqual(
            manifest["screenshots"],
            [
                "home-desktop.png",
                "home-mobile.png",
                "home-install-desktop.png",
                "home-install-mobile.png",
                "f01-desktop.png",
                "f01-mobile.png",
                "f02-desktop.png",
                "f02-mobile.png",
                "f03-desktop.png",
                "f03-mobile.png",
                "f04-desktop.png",
                "f04-mobile.png",
                "f04-proof-map-desktop.png",
                "f04-proof-map-mobile.png",
                "f04-repair-boundary-desktop.png",
                "f04-repair-boundary-mobile.png",
                "p01-desktop.png",
                "p01-mobile.png",
                "p02-desktop.png",
                "p02-mobile.png",
                "p03-desktop.png",
                "p03-mobile.png",
                "p04-desktop.png",
                "p04-mobile.png",
                "p05-desktop.png",
                "p05-mobile.png",
                "p06-desktop.png",
                "p06-mobile.png",
                "p07-desktop.png",
                "p07-mobile.png",
                "p08-desktop.png",
                "p08-mobile.png",
            ],
        )
        baseline_root = ROOT / "tests" / "site" / "__screenshots__"
        self.assertEqual(
            sorted(path.name for path in baseline_root.glob("*.png")),
            sorted(manifest["screenshots"]),
        )

    def test_pull_request_browser_job_is_parallel_deterministic_and_local_only(self) -> None:
        workflow = VERIFY_WORKFLOW.read_text(encoding="utf-8")
        browser = workflow_job(workflow, "academy-browser")

        self.assertNotIn("needs:", browser)
        self.assertIn("runs-on: ubuntu-24.04", browser)
        self.assertIn("timeout-minutes: 25", browser)
        self.assertIn("node-version: \"22.19.0\"", browser)
        self.assertIn("npm ci --ignore-scripts", browser)
        self.assertIn(
            "./node_modules/.bin/playwright install --with-deps --only-shell chromium",
            browser,
        )
        self.assertIn("./node_modules/.bin/playwright test", browser)
        self.assertIn(
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
            browser,
        )
        self.assertIn("workers: 1", (ROOT / "playwright.config.mjs").read_text(encoding="utf-8"))
        self.assertNotIn("cache:", browser)
        self.assertNotIn("academy-pages.yml", browser)
        self.assertNotIn("deploy", browser.casefold())


if __name__ == "__main__":
    unittest.main()
