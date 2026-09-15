<!-- release-targets -->
[academy-preview]
display-name: Arbiter Academy Preview
prefix: preview-
version-policy: numeric-sequence
initial-version: 0.1
manifest: academy/release.json
changelog: CHANGELOG.md
changelog-reconciliations: .codearbiter/release-changelog-reconciliations.json
payload: .
payload-exclude: .codearbiter/gate-events.log
payload-exclude: .codearbiter/.markers
latest-eligible: true
release-build: "$PY" scripts/build_release_assets.py --source . --output "$RELEASE_ASSET_DIR" --epoch 1789257600 --release "$RELEASE_TAG"
release-asset: install.ps1
release-asset: install.ps1.sha256
release-asset: install.sh
release-asset: install.sh.sha256
release-asset: arbiter-academy-preview-{version}.zip
release-asset: arbiter-academy-preview-{version}.zip.sha256
pre-tag: "$PY" -m unittest tests.test_preview_manifest tests.test_codearbiter_compatibility tests.test_preview_site tests.test_pages_workflow tests.test_release_declaration tests.test_release_assets tests.test_foundations_labs.PreviewCompatibilitySourceTests -v
pre-tag: "$PY" -m tabnanny academy_engine workshop_queue scripts tests
<!-- /release-targets -->
