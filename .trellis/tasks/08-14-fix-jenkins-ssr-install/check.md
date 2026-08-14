# Verification Log

## Passed

- `npx --yes npm@10.8.2 install --package-lock-only --ignore-scripts --no-audit --no-fund` from `g2-ssr`: passed.
- `npx --yes npm@10.8.2 ci --ignore-scripts --no-audit --no-fund` from `g2-ssr`: passed; 292 packages installed.
- `node --test tools/tests/jenkins_ssr_build_contract.test.mjs`: passed, 3 tests.
- `git diff --check`: passed.

## Not Run

- `docker buildx build --target ssr-builder ...`: not run locally. The installed Windows Docker command is malformed and returns `docker: unknown command: docker C:\Program Files\Docker\Docker\resources\bin\docker.exe` before contacting a daemon.

The Linux SSR-stage build must be run by Jenkins after this change is submitted to the `release/release_2.0.0` line. It is the final verification that the existing native development libraries compile canvas successfully with `npm_config_build_from_source=true`.

## Review Notes

- `g2-ssr/package-lock.json` is explicitly unignored at the repository root and is no longer ignored by the SSR-local `.gitignore`.
- The runtime spec records the lockfile, source-build, cache-mount, and 20-minute timeout contracts.
