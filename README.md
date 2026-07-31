# arbiter-academy
Real, fork-first training for codeArbiter.

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
