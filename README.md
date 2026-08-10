# arbiter-academy
Real, fork-first training for codeArbiter.

This repository is the public training home: it publishes the Academy course,
the runnable learner package, and the evidence-preserving recovery route. The
separate [codeArbiter reference site](https://codearbiter.dev/) explains the
governance concepts that the Academy lessons put into practice.

## Preview 0.2 quick start

Preview 0.2 publishes nine reviewed Foundations and Practitioner labs, each
paced for 15–60 minutes. P06–P07 are status-only; P08 and the Power User labs
are not included. The Preview is static, local training: it does not provide
hosted execution, hosted verification, or a signed credential.

You need Git, a GitHub account, codeArbiter, and Python 3.11 or newer. Run the
bootstrap below immediately after cloning, before making learner changes. It
requires the clone's clean `HEAD` to equal the current canonical Academy
`main`, copies that reviewed commit into a sibling source snapshot, and builds
the verifier there without reaching a package index. The installed verifier
and its build source then remain outside the learner repository.

1. Fork `arbiterForge/arbiter-academy` on GitHub.
2. Clone your fork with
   `git clone https://github.com/<your-account>/arbiter-academy.git`. Keep
   `origin` and every push destination pointed at your fork; the canonical
   Academy repository is reference-only. Change into the clone before
   continuing.
3. Verify, snapshot, and install the verifier in sibling directories. The
   bootstrap refuses a changed or stale fork, a dirty checkout, or pre-existing
   source/tools paths. The reviewed snapshot's committed `.github/wheelhouse`
   supplies Setuptools; `--no-index --no-deps` prevents package-index or
   dependency resolution.

   Windows PowerShell:

   ```powershell
   $ErrorActionPreference = "Stop"
   $academyCheckout = (Get-Location).Path
   $academyCanonical = "https://github.com/arbiterForge/arbiter-academy.git"
   $academyHead = (& git rev-parse --verify HEAD).Trim()
   if ($LASTEXITCODE -ne 0) { throw "Could not read the learner checkout commit." }
   & git fetch --quiet --no-tags $academyCanonical main
   if ($LASTEXITCODE -ne 0) { throw "Could not fetch the canonical Academy source." }
   $academyReviewedCommit = (& git rev-parse --verify FETCH_HEAD).Trim()
   if ($LASTEXITCODE -ne 0 -or $academyHead -ne $academyReviewedCommit) { throw "Fork HEAD is not the reviewed canonical Preview source." }
   $academyStatus = & git status --porcelain=v1 --untracked-files=all
   if ($LASTEXITCODE -ne 0 -or $academyStatus) { throw "Bootstrap requires a clean learner checkout." }
   $academyParent = Split-Path -Parent $academyCheckout
   $academySource = Join-Path $academyParent "arbiter-academy-source-preview-0.2"
   $academyTools = Join-Path $academyParent "arbiter-academy-tools-preview-0.2"
   if ((Test-Path -LiteralPath $academySource) -or (Test-Path -LiteralPath $academyTools)) { throw "Preview source/tools path already exists; preserve anything needed, then remove it before retrying." }
   & git clone --quiet --no-local $academyCheckout $academySource
   if ($LASTEXITCODE -ne 0) { throw "Could not create the reviewed source snapshot." }
   $academySnapshotCommit = (& git -C $academySource rev-parse --verify HEAD).Trim()
   if ($LASTEXITCODE -ne 0 -or $academySnapshotCommit -ne $academyReviewedCommit) { throw "Reviewed source snapshot identity mismatch." }
   & py -3 -m venv $academyTools
   if ($LASTEXITCODE -ne 0) { throw "Could not create the Academy tools environment." }
   $academyPython = Join-Path $academyTools "Scripts\python.exe"
   & $academyPython -m pip wheel --no-index --find-links "$academySource\.github\wheelhouse" --no-deps --wheel-dir "$academyTools\wheels" $academySource
   if ($LASTEXITCODE -ne 0) { throw "Could not build the reviewed Academy wheel." }
   & $academyPython -m pip install --no-index --no-deps "$academyTools\wheels\workshop_queue-0.1.0-py3-none-any.whl"
   if ($LASTEXITCODE -ne 0) { throw "Could not install the reviewed Academy wheel." }
   $academy = Join-Path $academyTools "Scripts\arbiter-academy.exe"
   ```

   macOS or Linux shell:

   ```sh
   set -eu
   academy_checkout="$PWD"
   academy_canonical="https://github.com/arbiterForge/arbiter-academy.git"
   academy_head="$(git rev-parse --verify HEAD)"
   git fetch --quiet --no-tags "$academy_canonical" main
   academy_reviewed_commit="$(git rev-parse --verify FETCH_HEAD)"
   test "$academy_head" = "$academy_reviewed_commit" || { echo "Fork HEAD is not the reviewed canonical Preview source." >&2; exit 1; }
   if ! academy_status="$(git status --porcelain=v1 --untracked-files=all)"; then echo "Could not inspect learner checkout status." >&2; exit 1; fi
   test -z "$academy_status" || { echo "Bootstrap requires a clean learner checkout." >&2; exit 1; }
   academy_parent="$(dirname "$academy_checkout")"
   academy_source="$academy_parent/arbiter-academy-source-preview-0.2"
   academy_tools="$academy_parent/arbiter-academy-tools-preview-0.2"
   test ! -e "$academy_source" && test ! -e "$academy_tools" || { echo "Preview source/tools path already exists; preserve anything needed, then remove it before retrying." >&2; exit 1; }
   git clone --quiet --no-local "$academy_checkout" "$academy_source"
   test "$(git -C "$academy_source" rev-parse --verify HEAD)" = "$academy_reviewed_commit" || { echo "Reviewed source snapshot identity mismatch." >&2; exit 1; }
   python3 -m venv "$academy_tools"
   academy_python="$academy_tools/bin/python"
   "$academy_python" -m pip wheel --no-index --find-links "$academy_source/.github/wheelhouse" --no-deps --wheel-dir "$academy_tools/wheels" "$academy_source"
   "$academy_python" -m pip install --no-index --no-deps "$academy_tools/wheels/workshop_queue-0.1.0-py3-none-any.whl"
   academy="$academy_tools/bin/arbiter-academy"
   ```

4. Prepare the selected lab. Replace the example lab ID when you choose a
   different published lesson:

   ```powershell
   & $academy --repository $academyCheckout prepare F01-fork-clone-doctor
   ```

   ```sh
   "$academy" --repository "$academy_checkout" prepare F01-fork-clone-doctor
   ```

   The general command form is:

   ```text
   arbiter-academy --repository <learner-repository> prepare <lab-id>
   ```

5. Work through the lesson with codeArbiter and Git, then run the installed
   verifier:

   ```text
   arbiter-academy --repository <learner-repository> check <lab-id>
   ```

6. If an attempt is blocked, preserve its evidence, return the checkout to a
   clean state, and begin a documented retry:

   ```text
   arbiter-academy --repository <learner-repository> reset <lab-id>
   ```

See the public recovery page for the complete recovery route. Questions and
Preview feedback belong in
[Academy GitHub Discussions](https://github.com/arbiterForge/arbiter-academy/discussions).

## Authoritative local verification

Before learner changes, the bootstrap verifies a clean canonical commit and
installs from its sibling source snapshot. Then select the learner repository
explicitly:

```text
arbiter-academy --repository <learner-repository> check <lab-id>
```

Graduation is not available in Preview 0.2. The current receipt requires the
complete 19-lab course through U07, while this release intentionally publishes
only nine verified labs. The `graduate` command remains reserved for the
complete course rather than issuing a partial or misleading Preview credential.

After bootstrap, the external snapshot and installed verifier form the local
trust anchor; the selected learner checkout and its Git/artifact data are
untrusted inputs. This boundary assumes the initial canonical fetch, Git,
Python, and local machine were not replaced by a malicious operator. It does
not provide cryptographic or malicious-operator resistance. When the complete
course is published, graduation receipts will label the model as
`installed-local-verifier`; they are deterministic, tamper-evident local
evidence, not cryptographically signed credentials.

Repository-local tooling remains available for preparation, reset, update,
progress, doctor, and catalog export. It refuses to present an in-checkout
`check` or `graduate` run as authoritative.

## Maintainer release verification

The serial `python -m unittest discover -v` command remains the canonical
inventory reference. Maintainers can run that same inventory as eight
dependency-free concurrent shards with exact-once result evidence:

```text
python scripts/run_test_shards.py --all --evidence-dir .superpowers/shard-evidence --timeout-seconds 5400
```
