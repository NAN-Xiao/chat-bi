# Technical Design

## Root Cause Boundary

The failure occurs inside the `ssr-builder` dependency layer. `canvas@2.11.2` runs `node-pre-gyp`, which prefers a GitHub-hosted prebuilt archive. The TCP connection can remain established after payload delivery stops, and neither the package install nor the Jenkins stage currently imposes a useful upper bound.

The fix therefore addresses both the dependency path and the pipeline boundary:

1. Remove the problematic binary-host dependency from the normal build path by compiling native modules from source.
2. Make dependency resolution deterministic with a committed lockfile and `npm ci`.
3. Add a pipeline timeout so a different future hang cannot consume an executor indefinitely.

## Docker Dependency Flow

`g2-ssr/package.json` and `g2-ssr/package-lock.json` are copied before application source. The install layer runs with:

```text
BuildKit npm cache -> npm ci -> lifecycle scripts receive npm_config_build_from_source=true
                                   -> canvas invokes node-gyp locally
                                   -> no GitHub Release binary request
```

The existing build dependencies in `ssr-builder` remain authoritative. No binary fallback is added: source compilation failure must fail the image build explicitly.

## Jenkins Boundary

Use declarative stage `options { timeout(time: 20, unit: 'MINUTES') }` on “构建 Docker 镜像”. Historical successful builds complete the stage in roughly five minutes; 20 minutes leaves room for a cold source build while bounding executor occupation.

The timeout is not the primary fix and must not replace the source-build and lockfile changes.

## Verification Strategy

- A repository-level source contract test reads `Dockerfile`, `Jenkinsfile`, and the SSR lockfile.
- The test asserts semantic build invariants rather than exact whitespace.
- Run `npm ci --ignore-scripts` in a temporary copy or clean SSR directory to validate lock consistency without invoking native compilation on Windows.
- If Docker is available, build the SSR stage to prove native compilation succeeds in the Linux toolchain.

## Compatibility And Rollback

- Node remains `18.20.8`; package versions remain those resolved by the generated lockfile.
- Runtime image contents and `/opt/shuzhi/g2-ssr` layout do not change.
- Rollback is a normal Git revert of the Dockerfile, Jenkinsfile, lockfile, test, and spec/task records.
- Reverting only the timeout is insufficient if the binary download path is restored; the three build guarantees are treated as one change unit.
