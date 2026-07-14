import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/elex/Downloads/tracking_dictionary_current (7).xlsx";
const outputPath = "D:/AIWork3/chat-bi/outputs/first_zombie_fix/tracking_dictionary_current (7)_fixed.xlsx";
const analysisPath = "D:/AIWork3/chat-bi/outputs/first_zombie_fix/source_analysis.json";

const analysis = JSON.parse(await fs.readFile(analysisPath, "utf8"));
const targetRows = analysis.flatMap((item) => item.wrong_rows ?? []);

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("事件参数对照");

for (const rowNumber of targetRows) {
  sheet.getRange(`E${rowNumber}`).values = [["personal"]];
}

const after = sheet.getRange("E1:E848").values;
const verified = targetRows.every((rowNumber) => after[rowNumber - 1]?.[0] === "personal");
if (!verified) {
  throw new Error("修复后仍有数据源字段未更新为 personal");
}

await fs.mkdir("D:/AIWork3/chat-bi/outputs/first_zombie_fix", { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log(`OUTPUT\t${outputPath}`);
console.log(`FIXED_ROWS\t${targetRows.length}`);
console.log(`VERIFIED\t${verified}`);

const ranges = ["A1:I120", "A130:I180", "A370:I410", "A490:I545", "A560:I610", "A650:I690", "A730:I760"];
for (const range of ranges) {
  const preview = await workbook.render({ sheetName: "事件参数对照", range, scale: 1, format: "png" });
  const safe = range.replace(":", "_");
  await fs.writeFile(`D:/AIWork3/chat-bi/outputs/first_zombie_fix/verified_${safe}.png`, new Uint8Array(await preview.arrayBuffer()));
}
