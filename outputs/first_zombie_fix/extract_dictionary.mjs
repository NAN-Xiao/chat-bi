import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("C:/Users/elex/Downloads/tracking_dictionary_current (7).xlsx");
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("事件参数对照");
const values = sheet.getRange("A1:I848").values;
await fs.writeFile(
  "D:/AIWork3/chat-bi/outputs/first_zombie_fix/dictionary_rows.json",
  JSON.stringify(values, null, 2),
  "utf8",
);
console.log(`ROWS\t${values.length}`);
console.log(`HEADER\t${JSON.stringify(values[0])}`);
