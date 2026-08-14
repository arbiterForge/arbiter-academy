# Hosted verification wheelhouse

This directory contains the reviewed build-only prerequisite for Academy's
offline installation proofs. It is not a runtime dependency and is not included
in the `workshop-queue` distribution.

- File: `setuptools-83.0.0-py3-none-any.whl`
- Size: `1008090` bytes
- SHA-256: `29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3`
- Official PyPI release: <https://pypi.org/project/setuptools/83.0.0/>
- Official wheel: <https://files.pythonhosted.org/packages/5d/40/e1e72872c6354b306daef1703549e8e83b4d43cfea356311bf722a043752/setuptools-83.0.0-py3-none-any.whl>
- Upstream signed tag: <https://github.com/pypa/setuptools/releases/tag/v83.0.0>
- Local review record: the dedicated locally verified SD-146 wheelhouse

The installation tests verify this identity before use and retain
`--no-index --no-deps`. The wheel contains its upstream license payload.
