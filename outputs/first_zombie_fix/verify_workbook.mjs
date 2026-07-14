import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load("D:/AIWork3/chat-bi/outputs/first_zombie_fix/tracking_dictionary_current (7)_fixed.xlsx"),
);
const sheet = workbook.worksheets.getItem("事件参数对照");
const values = sheet.getRange("A1:I848").values;
const analysis = JSON.parse(await fs.readFile("D:/AIWork3/chat-bi/outputs/first_zombie_fix/source_analysis.json", "utf8"));
const targetRows = new Set(analysis.flatMap((item) => item.wrong_rows ?? []));

let currentEvent = null;
let verifiedTargets = 0;
let sampledEventSourceMismatches = [];
for (let i = 1; i < values.length; i += 1) {
  const row = values[i];
  if (row[0]) currentEvent = String(row[0]).trim();
  const rowNumber = i + 1;
  if (targetRows.has(rowNumber) && row[4] === "personal") verifiedTargets += 1;
  const evidence = analysis.find((item) => item.event === currentEvent && item.expected_source === "personal");
  if (evidence && row[5] && row[4] !== "personal") {
    sampledEventSourceMismatches.push(`${rowNumber}:${currentEvent}:${row[5]}=${row[4]}`);
  }
}

console.log(`TARGET_ROWS\t${targetRows.size}`);
console.log(`TARGET_ROWS_VERIFIED\t${verifiedTargets}`);
console.log(`SAMPLED_EVENT_SOURCE_MISMATCHES\t${sampledEventSourceMismatches.length}`);
console.log(`WORLD_MARCH_RET\t${JSON.stringify(values.slice(58, 76).map((row) => [row[0], row[4], row[5]]))}`);
console.log((await workbook.inspect({
  kind: "region",
  sheetId: "事件参数对照",
  range: "A55:I76",
  maxChars: 5000,
  tableMaxRows: 30,
  tableMaxCols: 9,
  tableMaxCellChars: 80,
})).ndjson);

if (verifiedTargets !== targetRows.size || sampledEventSourceMismatches.length !== 0) {
  throw new Error("导出文件复核失败");
}
