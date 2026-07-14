import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load("C:/Users/elex/Downloads/tracking_dictionary_current (7).xlsx"),
);
const sheet = workbook.worksheets.getItem("事件参数对照");
const values = sheet.getRange("E1:E848").values;
const targetRows = [2, 3, 4, 5, 6, 7, 8, 9, 10, 61, 63, 64, 74, 748, 749, 751];
const failed = targetRows.filter((row) => values[row - 1]?.[0] !== "personal");
console.log(`CHECKED\t${targetRows.length}`);
console.log(`FAILED\t${failed.length}`);
if (failed.length) throw new Error(`原路径仍有未覆盖行: ${failed.join(",")}`);
