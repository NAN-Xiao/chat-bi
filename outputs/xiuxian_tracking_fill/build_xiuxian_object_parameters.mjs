import { spawnSync } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const OUTPUT_PATH = path.join(__dirname, "tracking_dictionary_template_xiuxian.xlsx");
const SUMMARY_PATH = path.join(__dirname, "xiuxian_object_sampling_summary.json");
const CHECK_PATH = path.join(__dirname, "xiuxian_object_parameter_check.ndjson");
const PREVIEW_PATH = path.join(__dirname, "preview_tracking_dictionary_template_xiuxian.png");
const DEFAULT_SOURCE_PATH = "D:/AIWork3/djinchao/chat-bi/docs/修仙项目-BI打点整理.xlsx";
const DEFAULT_TEMPLATE_PATH = "D:/AIWork3/djinchao/chat-bi/docs/tracking_dictionary_template.xlsx";
const DEFAULT_PYTHON = "D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe";

const SAMPLE_PYTHON = String.raw`
import datetime
import json
import os
import sys

import pymysql

request = json.loads(sys.stdin.read())
pairs = request["pairs"]
events = sorted({pair["eventName"] for pair in pairs})
connection = pymysql.connect(
    host=os.environ["XIUXIAN_DB_HOST"],
    port=int(os.environ.get("XIUXIAN_DB_PORT", "3306")),
    user=os.environ["XIUXIAN_DB_USER"],
    password=os.environ["XIUXIAN_DB_PASSWORD"],
    database=os.environ["XIUXIAN_DB_NAME"],
    charset="utf8mb4",
    connect_timeout=10,
    read_timeout=120,
    write_timeout=20,
)
cursor = connection.cursor()
cursor.execute("SELECT MAX(dt) FROM user")
anchor_dt = int(cursor.fetchone()[0])
start_dt = int((datetime.datetime.strptime(str(anchor_dt), "%Y%m%d").date() - datetime.timedelta(days=27)).strftime("%Y%m%d"))
placeholders = ",".join(["%s"] * len(events))
cursor.execute(
    "SELECT event, personal FROM event WHERE dt BETWEEN %s AND %s AND event IN (" + placeholders + ") LIMIT 5000",
    [start_dt, anchor_dt, *events],
)
pairs_by_event = {}
for pair in pairs:
    pairs_by_event.setdefault(pair["eventName"], set()).add(pair["propertyName"])
samples = {(pair["eventName"], pair["propertyName"]): [] for pair in pairs}
for event_name, personal in cursor.fetchall():
    try:
        payload = json.loads(personal)
    except (TypeError, ValueError):
        continue
    for property_name in pairs_by_event.get(event_name, set()):
        key = (event_name, property_name)
        if property_name in payload and len(samples[key]) < 3:
            samples[key].append(payload[property_name])
items = []
for pair in pairs:
    key = (pair["eventName"], pair["propertyName"])
    items.append({**pair, "samples": samples[key]})
print(json.dumps({"anchorDt": anchor_dt, "startDt": start_dt, "items": items}, ensure_ascii=False))
`;

function text(value) {
  return value === null || value === undefined ? "" : String(value).replace(/\r\n/g, "\n").trim();
}

function objectKey(eventName, propertyName) {
  return `${eventName}\u0000${propertyName}`;
}

export function collectObjectParameters(rows) {
  let currentEventName = "";
  const parameters = [];
  for (const row of rows.slice(1)) {
    if (text(row[3])) currentEventName = text(row[3]);
    if (currentEventName && text(row[7]).toLowerCase() === "object" && text(row[5])) {
      parameters.push({
        eventName: currentEventName,
        propertyName: text(row[5]),
        parentDescription: text(row[6]),
        parentRemark: text(row[8]),
      });
    }
  }
  return parameters;
}

function parseNestedJson(value) {
  if (typeof value !== "string") return value;
  const candidate = value.trim();
  if (!candidate || !["{", "["].includes(candidate[0])) return value;
  try {
    return JSON.parse(candidate);
  } catch {
    return value;
  }
}

function scalarType(value) {
  if (typeof value === "boolean") return "布尔";
  if (typeof value === "number") return "数值";
  return "文本";
}

export function flattenJson(value, currentPath) {
  const parsed = parseNestedJson(value);
  if (Array.isArray(parsed)) {
    const leaves = parsed.flatMap((item) => flattenJson(item, `${currentPath}[]`));
    return leaves.length ? leaves : [{ path: `${currentPath}[]`, type: "对象组", example: null }];
  }
  if (parsed && typeof parsed === "object") {
    return Object.entries(parsed).flatMap(([key, item]) => flattenJson(item, `${currentPath}.${key}`));
  }
  return [{ path: currentPath, type: scalarType(parsed), example: parsed }];
}

function mergeLeaves(propertyName, samples) {
  const leaves = new Map();
  for (const sample of samples) {
    for (const leaf of flattenJson(sample, propertyName)) {
      const entry = leaves.get(leaf.path) || { path: leaf.path, type: leaf.type, examples: [] };
      if (entry.type === "文本" && leaf.type !== "文本") entry.type = leaf.type;
      if (leaf.example !== null && leaf.example !== undefined && entry.examples.length < 3) {
        const comparable = JSON.stringify(leaf.example);
        if (!entry.examples.some((example) => JSON.stringify(example) === comparable)) entry.examples.push(leaf.example);
      }
      leaves.set(leaf.path, entry);
    }
  }
  return [...leaves.values()];
}

export function sanitizeLeafExamples(parentDescription, leaves) {
  const descriptionSignalsIdentity = /(?:玩家|用户|好友|friend).{0,8}(?:id|ID)|\buid\b/i.test(parentDescription);
  return leaves.map((leaf) => {
    const normalizedPath = leaf.path.toLowerCase();
    const knownBusinessId = /(itemid|heroid|petid|goodid|boxid|attributeid)/.test(normalizedPath);
    const identityPath = /(friendid|playerid|userid|\buid\b)/.test(normalizedPath);
    if ((descriptionSignalsIdentity && /id/.test(normalizedPath) && !knownBusinessId) || identityPath) {
      return { ...leaf, examples: [] };
    }
    return leaf;
  });
}

function leafToken(pathValue) {
  return pathValue.replace(/^.*(?:\.|\[\])/, "");
}

const LEAF_MEANINGS = new Map([
  ["WORLD_ZHU_GUO", "世界资源：朱果"],
  ["WORLD_FU_MU", "世界资源：扶木"],
  ["WORLD_BAO_JING", "世界资源：宝晶"],
  ["itemId", "物品 ID"],
  ["itemid", "物品 ID"],
  ["itemNum", "物品数量"],
  ["goodid", "商品 ID"],
  ["goodnum", "商品数量"],
  ["seat", "阵位"],
  ["star", "星级"],
  ["level", "等级"],
  ["heroid", "长老 ID"],
  ["petid", "灵兽 ID"],
  ["petId", "灵兽 ID"],
  ["num", "数量"],
  ["baoDiType", "保底类型"],
]);

function leafMeaning(pathValue) {
  const token = leafToken(pathValue);
  if (LEAF_MEANINGS.has(token)) return LEAF_MEANINGS.get(token);
  if (/^\d+$/.test(token)) return `游戏内效果/枚举 ID：${token}`;
  return `JSON 子字段：${token}`;
}

function descriptionFor(parentDescription, parentRemark, leaf) {
  const parts = [];
  if (parentDescription) parts.push(`参数说明：${parentDescription}`);
  else if (parentRemark) parts.push(parentRemark);
  parts.push(`子字段含义：${leafMeaning(leaf.path)}`);
  if (leaf.examples.length) parts.push(`样例：${leaf.examples.map(String).join(", ")}`);
  return parts.join("；");
}

function displayNameFor(leaf) {
  return leafMeaning(leaf.path);
}

function baseDescription(row) {
  const description = text(row[8]);
  return description || "参数说明未提供";
}

export function expandEventParameterRows(rows, sampled) {
  const expanded = [rows[0]];
  let currentEventName = "";
  for (const row of rows.slice(1)) {
    const normalized = [...row];
    if (text(normalized[0])) currentEventName = text(normalized[0]);
    const key = objectKey(currentEventName, text(normalized[5]));
    const sample = sampled.get(key);
    if (sample?.sampleCount > 0 && sample.leaves.length) {
      sample.leaves.forEach((leaf, index) => {
        const child = [...normalized];
        if (index > 0) child.splice(0, 4, "", "", "", "");
        child[4] = "personal";
        child[5] = leaf.path;
        child[6] = displayNameFor(leaf);
        child[7] = leaf.type;
        child[8] = descriptionFor(sample.parentDescription, sample.parentRemark, leaf);
        expanded.push(child);
      });
      continue;
    }
    if (sample?.sampleCount === 0) {
      normalized[8] = `${baseDescription(normalized)}；近 28 天未采样到 JSON 子字段，保留对象参数`;
    }
    expanded.push(normalized);
  }
  return expanded;
}

function a1Column(index) {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function rangeAddress(rows) {
  return `A1:${a1Column(rows[0].length - 1)}${rows.length}`;
}

function findGroups(rows) {
  const groups = [];
  let current = null;
  for (let index = 1; index < rows.length; index += 1) {
    const rowNumber = index + 1;
    if (text(rows[index][0])) {
      if (current) groups.push(current);
      current = { start: rowNumber, end: rowNumber };
    } else if (current && text(rows[index][5])) {
      current.end = rowNumber;
    } else if (current) {
      groups.push(current);
      current = null;
    }
  }
  if (current) groups.push(current);
  return groups;
}

function runSampling(parameters) {
  const python = process.env.PYTHON_EXECUTABLE || DEFAULT_PYTHON;
  const result = spawnSync(python, ["-c", SAMPLE_PYTHON], {
    input: JSON.stringify({ pairs: parameters }),
    encoding: "utf8",
    env: process.env,
    timeout: 130000,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr || "修仙事件采样失败");
  return JSON.parse(result.stdout);
}

function sampledMap(sampleResult) {
  const map = new Map();
  for (const item of sampleResult.items) {
    const leaves = sanitizeLeafExamples(item.parentDescription, mergeLeaves(item.propertyName, item.samples));
    map.set(objectKey(item.eventName, item.propertyName), {
      ...item,
      sampleCount: item.samples.length,
      leaves,
    });
  }
  return map;
}

async function loadWorkbook(filePath) {
  return SpreadsheetFile.importXlsx(await FileBlob.load(filePath));
}

function applyEventParameterFormatting(sheet, rows) {
  const allRange = sheet.getRange(rangeAddress(rows));
  sheet.showGridLines = false;
  allRange.format.wrapText = true;
  sheet.freezePanes.freezeRows(1);
  for (const group of findGroups(rows)) {
    const groupRange = sheet.getRange(`A${group.start}:D${group.end}`);
    groupRange.format.borders = { preset: "none" };
    groupRange.format.borders = {
      top: { style: "thin", color: "#BFBFBF" },
      bottom: { style: "thin", color: "#BFBFBF" },
      left: { style: "thin", color: "#D9D9D9" },
      right: { style: "thin", color: "#D9D9D9" },
      insideVertical: { style: "thin", color: "#D9D9D9" },
    };
    groupRange.format.horizontalAlignment = "left";
  }
  sheet.getRange("A:A").format.columnWidth = 22;
  sheet.getRange("B:B").format.columnWidth = 28;
  sheet.getRange("C:C").format.columnWidth = 34;
  sheet.getRange("D:D").format.columnWidth = 18;
  sheet.getRange("E:E").format.columnWidth = 14;
  sheet.getRange("F:F").format.columnWidth = 28;
  sheet.getRange("G:G").format.columnWidth = 30;
  sheet.getRange("H:H").format.columnWidth = 14;
  sheet.getRange("I:I").format.columnWidth = 76;
  allRange.format.autofitRows();
}

async function main() {
  const sourcePath = process.env.XIUXIAN_SOURCE_PATH || DEFAULT_SOURCE_PATH;
  const templatePath = process.env.XIUXIAN_TEMPLATE_PATH || DEFAULT_TEMPLATE_PATH;
  const sourceWorkbook = await loadWorkbook(sourcePath);
  const backendRows = sourceWorkbook.worksheets.getItem("后端").getUsedRange(true).values;
  const parameters = collectObjectParameters(backendRows);
  const sampleResult = runSampling(parameters);
  const samples = sampledMap(sampleResult);
  const summary = {
    anchorDt: sampleResult.anchorDt,
    startDt: sampleResult.startDt,
    sourceObjectParameterCount: parameters.length,
    sampledObjectParameterCount: [...samples.values()].filter((item) => item.sampleCount > 0).length,
    items: [...samples.values()].map(({ samples: _samples, ...item }) => item),
  };
  await fs.writeFile(SUMMARY_PATH, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
  if (process.argv.includes("--sample-only")) return;

  const workbook = await loadWorkbook(templatePath);
  const sheet = workbook.worksheets.getItem("事件参数对照");
  const originalRows = sheet.getUsedRange(true).values;
  const outputRows = expandEventParameterRows(originalRows, samples);
  const usedRange = sheet.getUsedRange(true);
  if (usedRange) usedRange.clear({ applyTo: "contents" });
  sheet.getRange(rangeAddress(outputRows)).values = outputRows;
  for (const table of [...sheet.tables.items]) table.delete();
  sheet.tables.add(rangeAddress(outputRows), true, "EventParameterMappingTable");
  applyEventParameterFormatting(sheet, outputRows);

  const check = await workbook.inspect({
    kind: "match",
    searchTerm: "ed_change\\.WORLD_ZHU_GUO|ed_drawResult\\[\\]\\.itemId|近 28 天未采样到 JSON 子字段",
    options: { useRegex: true, maxResults: 100 },
    maxChars: 8000,
  });
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    maxChars: 2000,
  });
  await fs.writeFile(CHECK_PATH, `${check.ndjson}\n${formulaErrors.ndjson}`, "utf8");
  const preview = await workbook.render({ sheetName: "事件参数对照", range: "A1:I100", scale: 1, format: "png" });
  await fs.writeFile(PREVIEW_PATH, new Uint8Array(await preview.arrayBuffer()));
  const exported = await SpreadsheetFile.exportXlsx(workbook);
  await exported.save(OUTPUT_PATH);
  console.log(JSON.stringify({ outputPath: OUTPUT_PATH, summary, check: check.ndjson, formulaErrors: formulaErrors.ndjson }, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  await main();
}
