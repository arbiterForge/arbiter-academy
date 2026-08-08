# arbiter-academy
Real, fork-first training for codeArbiter.

## Preview 0.1 quick start

Preview 0.1 publishes eight reviewed Foundations and Practitioner labs, each
paced for 20–35 minutes. P05–P07 are status-only; P08 and the Power User labs
are not included. The Preview is static, local training: it does not provide
hosted execution, hosted verification, or a signed credential.

You need Git, a GitHub account, codeArbiter, and the reviewed
`arbiter-academy` package installed outside the learner checkout.

1. Fork `arbiterForge/arbiter-academy` on GitHub.
2. Clone your fork with
   `git clone https://github.com/<your-account>/arbiter-academy.git`. Keep
   `origin` and every push destination pointed at your fork; the canonical
   Academy repository is reference-only.
3. Prepare the selected lab:

   ```text
   arbiter-academy --repository <learner-repository> prepare <lab-id>
   ```

4. Work through the lesson with codeArbiter and Git, then run the installed
   verifier:

   ```text
   arbiter-academy --repository <learner-repository> check <lab-id>
   ```

5. If an attempt is blocked, preserve its evidence, return the checkout to a
   clean state, and begin a documented retry:

   ```text
   arbiter-academy --repository <learner-repository> reset <lab-id>
   ```

See the public recovery page for the complete recovery route. Questions and
Preview feedback belong in
[Academy GitHub Discussions](https://github.com/arbiterForge/arbiter-academy/discussions).

## Authoritative local verification

Build and install the reviewed `arbiter-academy` wheel outside the learner
checkout, then select the learner repository explicitly:

```text
arbiter-academy --repository <learner-repository> check <lab-id>
arbiter-academy --repository <learner-repository> graduate
```

The installed verifier is the local trust anchor; the selected checkout and
its Git/artifact data are untrusted inputs. Graduation receipts label this as
`installed-local-verifier`. They are deterministic, tamper-evident evidence
under that boundary, not cryptographically signed credentials.

Repository-local tooling remains available for preparation, reset, update,
progress, doctor, and catalog export. It refuses to present an in-checkout
`check` or `graduate` run as authoritative.
