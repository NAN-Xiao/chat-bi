# Jenkins SSR Stall Evidence

## Observed Builds

- Job: `chat-bi`
- Build #82 entered `ssr-builder 7/7 RUN npm install`, remained there for about 34 minutes, then was aborted.
- Build #83 repeated the same stage on commit `a0991d8a` and remained active for more than 31 minutes during inspection.

## Process Evidence

- Process chain: `docker buildx build` -> BuildKit executor -> `npm install` -> `node-pre-gyp`.
- Package lifecycle log: `canvas@2.11.2 install node_modules/canvas node-pre-gyp install --fallback-to-build --update-binary`.
- The direct `node-canvas@2.9.0` source build completed successfully; the hanging child owned `/app/node_modules/canvas`.
- TCP peer: GitHub CDN `185.199.109.133:443`.
- Connection received about 7.1 MB, then showed no receive activity for more than 26 minutes while remaining `ESTAB`.
- Expected archive size: about 48.7 MB. A separate download from the same Jenkins host through `185.199.111.133` completed in about 15 seconds.

## Excluded Causes

- Host load average was below 0.5.
- Root filesystem had about 46 GB free and low inode usage.
- Build process CPU was effectively idle.
- The triggering commit only changed knowledge-editor frontend files, not SSR dependency declarations.

## Repository Findings

- `g2-ssr` has no lockfile and uses `npm install`.
- The main frontend already commits `package-lock.json` and uses `npm ci`.
- The SSR Docker stage installs the native build toolchain required by canvas.
- The Jenkins image-build stage has no declarative timeout.

## Conclusion

The immediate root cause is an indefinitely stalled GitHub-hosted canvas prebuilt-binary transfer. The durable fix is to remove that transfer from the build path, lock dependency resolution, and bound the pipeline stage so future external stalls fail explicitly.
