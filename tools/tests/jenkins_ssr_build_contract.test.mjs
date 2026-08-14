import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const dockerfile = fs.readFileSync(path.join(repositoryRoot, "Dockerfile"), "utf8");
const jenkinsfile = fs.readFileSync(path.join(repositoryRoot, "Jenkinsfile"), "utf8");
const ssrLockfile = JSON.parse(
  fs.readFileSync(path.join(repositoryRoot, "g2-ssr", "package-lock.json"), "utf8"),
);

function extractStage(source, stageName) {
  const stageStart = source.indexOf(`stage('${stageName}')`);
  assert.notEqual(stageStart, -1, `missing Jenkins stage: ${stageName}`);
  const nextStage = source.indexOf("\n    stage(", stageStart + 1);
  return source.slice(stageStart, nextStage === -1 ? source.length : nextStage);
}

test("SSR Docker install is locked, cached, and independent of prebuilt canvas binaries", () => {
  const ssrBuilder = dockerfile.slice(
    dockerfile.indexOf("# Build g2-ssr"),
    dockerfile.indexOf("# Runtime stage"),
  );

  assert.match(ssrBuilder, /COPY[^\n]*g2-ssr\/package-lock\.json[^\n]*\/app\//);
  assert.match(ssrBuilder, /--mount=type=cache,target=\/root\/\.npm/);
  assert.match(ssrBuilder, /npm_config_build_from_source=true/);
  assert.match(ssrBuilder, /\bnpm ci\b/);
  assert.doesNotMatch(ssrBuilder, /RUN\s+npm install\b/);
});

test("SSR lockfile records a reproducible dependency graph", () => {
  assert.equal(ssrLockfile.lockfileVersion, 3);
  assert.equal(ssrLockfile.packages?.[""].name, "vite-project");
  assert.ok(ssrLockfile.packages?.["node_modules/canvas"]);
  assert.ok(ssrLockfile.packages?.["node_modules/node-canvas"]);
});

test("Jenkins bounds the Docker image build stage", () => {
  const buildStage = extractStage(jenkinsfile, "构建 Docker 镜像");

  assert.match(buildStage, /options\s*\{[\s\S]*timeout\(time:\s*20,\s*unit:\s*'MINUTES'\)/);
});
