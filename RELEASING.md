# Releasing

Releases are published to [PyPI](https://pypi.org/project/btcmonitor/) by the `Release` GitHub Actions workflow whenever a GitHub release is published. It uses PyPI [trusted publishing](https://docs.pypi.org/trusted-publishers/), so there is no API token to store or rotate.

## One-time setup

1. **PyPI:** sign in at pypi.org, open *Your account → Publishing*, and add a *pending publisher* (it turns into a regular one with the first upload):
   - PyPI project name: `btcmonitor`
   - Owner: `afalk42`
   - Repository name: `btcmonitor`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
2. **GitHub:** under *Settings → Environments*, create an environment named `pypi` with these deployment protection rules:
   - *Required reviewers*: yourself, so every upload waits for your approval (leave *Prevent self-review* off, or a sole maintainer can never approve).
   - *Deployment branches and tags*: *Selected branches and tags* with a **tag** rule `v*`. The workflow runs on the release tag, so *Protected branches only* would block every release.

## Each release

1. Update `version` in `pyproject.toml` and add a section to `CHANGELOG.md`; merge that to `main`.
2. Create a GitHub release with a tag of the form `v<version>` (e.g. `v0.9.0`) targeting `main`, and paste the changelog section as its notes. From the command line:

   ```bash
   gh release create v0.9.0 --target main --title "btcmonitor 0.9.0" \
     --notes "$(awk -v v=0.9.0 '/^## /{p = ($2 == v); next} p' CHANGELOG.md)"
   ```

3. The workflow checks that the tag matches the package version, runs the tests, builds the sdist and wheel, checks them with `twine check --strict`, and uploads them to PyPI.

PyPI never accepts the same version twice, so a mistake means bumping the version (e.g. to 0.9.1) rather than re-uploading.

To check the package locally before releasing:

```bash
python -m pip install build twine
python -m build
twine check --strict dist/*
```
