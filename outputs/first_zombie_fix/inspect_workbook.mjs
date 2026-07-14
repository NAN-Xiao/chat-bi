import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/elex/Downloads/tracking_dictionary_current (7).xlsx";
const outputDir = "D:/AIWork3/chat-bi/outputs/first_zombie_fix";
await fs.mkdir(outputDir, { recursive: true });

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

console.log("SHEETS");
console.log((await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 5000 })).ndjson);
console.log("SUMMARY");
console.log((await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 10000,
  tableMaxRows: 8,
  tableMaxCols: 12,
  tableMaxCellChars: 100,
})).ndjson);

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange();
  if (!used) continue;
  console.log(`USED ${sheet.name} ${used.address}`);
  console.log((await workbook.inspect({
    kind: "region",
    sheetId: sheet.name,
    range: used.address,
    maxChars: 5000,
    tableMaxRows: 10,
    tableMaxCols: 12,
    tableMaxCellChars: 120,
  })).ndjson);
  const range = sheet.name.includes("事件") ? "A1:I120" : used.address;
  const preview = await workbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${sheet.name.replace(/[\\/:*?"<>|]/g, "_")}.png`, new Uint8Array(await preview.arrayBuffer()));
}
