# Implementation Plan

## Steps

- [x] Generate `g2-ssr/package-lock.json` with npm 10.8.2, compatible with the Node 18.20.8 base image, and validate the lockfile is clean.
- [x] Update the SSR Docker layer to copy the lockfile, mount the npm cache, use `npm ci`, and force native dependencies to build from source.
- [x] Add a 20-minute declarative timeout to the Jenkins Docker image build stage.
- [x] Add a focused build-contract regression test for the Dockerfile, Jenkinsfile, and SSR lockfile invariants.
- [x] Record the reusable CI rule in the applicable Trellis runtime spec.
- [x] Run lockfile validation, focused tests, and Dockerfile/Jenkinsfile checks; Docker image build remains pending because the local Docker CLI is unavailable.
- [x] Record commands and results in `check.md` and implementation notes.

## Validation Commands

```powershell
npx --yes npm@10.8.2 --prefix g2-ssr ci --ignore-scripts
node --test tools/tests/jenkins_ssr_build_contract.test.mjs
git diff --check
docker buildx build --target ssr-builder --progress=plain --load -t chat-bi-ssr-build-check .
```

The Docker command is conditional on a reachable Docker daemon and the required local base image tags. If unavailable locally, record the limitation and validate on Jenkins after the change is merged.

## Risk And Rollback Points

- Native canvas compilation can expose a missing Linux development package. The existing Dockerfile package list is expected to be sufficient; the SSR-stage build is the decisive check.
- Lock generation with the wrong npm major can create unnecessary churn. Generate with npm 10.8.2 to match the Node 18 base toolchain.
- Jenkins declarative syntax must place `options` directly inside the stage. A source contract test plus Jenkinsfile inspection guards this shape.
