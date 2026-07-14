import assert from "node:assert/strict";
import test from "node:test";

import {
  collectObjectParameters,
  expandEventParameterRows,
  flattenJson,
  sanitizeLeafExamples,
} from "./build_xiuxian_object_parameters.mjs";

test("collectObjectParameters inherits the current backend event name", () => {
  const rows = [
    ["级别", "", "", "事件名称(event)", "", "参数名", "参数说明", "参数类型", "备注说明"],
    ["", "", "资源", "ResourceChange", "资源变化", "ed_change", "资源变化量", "object", ""],
    ["", "", "", "", "", "ed_stock", "资源存量", "object", ""],
  ];

  assert.deepEqual(collectObjectParameters(rows), [
    { eventName: "ResourceChange", propertyName: "ed_change", parentDescription: "资源变化量", parentRemark: "" },
    { eventName: "ResourceChange", propertyName: "ed_stock", parentDescription: "资源存量", parentRemark: "" },
  ]);
});

test("flattenJson parses nested JSON strings into leaf paths", () => {
  assert.deepEqual(flattenJson('{"goodid":2,"goodnum":3}', "ed_marketSaleOld"), [
    { path: "ed_marketSaleOld.goodid", type: "数值", example: 2 },
    { path: "ed_marketSaleOld.goodnum", type: "数值", example: 3 },
  ]);
});

test("sanitizeLeafExamples removes user identifiers from exported samples", () => {
  const leaves = [
    { path: "ed_friendId[]", type: "文本", examples: ["12095788941414"] },
    { path: "ed_drawResult[].itemId", type: "数值", examples: [620101] },
  ];

  assert.deepEqual(sanitizeLeafExamples("对方玩家id", leaves), [
    { path: "ed_friendId[]", type: "文本", examples: [] },
    { path: "ed_drawResult[].itemId", type: "数值", examples: [620101] },
  ]);
});

test("expandEventParameterRows expands sampled objects and preserves unsampled parents", () => {
  const rows = [
    ["事件名（必填）", "事件显示名", "事件说明", "事件标签", "数据源字段", "属性名（必填）", "属性显示名", "属性类型（必填）", "属性说明"],
    ["ResourceChange", "资源变化", "", "资源", "personal", "ed_change", "资源变化量", "对象组", "参数说明：资源变化量"],
    ["EnergyChange", "体力变化", "", "资源", "personal", "ed_change", "体力变化量", "对象组", "参数说明：体力变化量"],
  ];
  const sampled = new Map([
    [
      "ResourceChange\u0000ed_change",
      {
        sampleCount: 1,
        leaves: [
          { path: "ed_change.WORLD_ZHU_GUO", type: "数值", examples: [302] },
          { path: "ed_change.WORLD_FU_MU", type: "数值", examples: [278] },
        ],
      },
    ],
    [
      "EnergyChange\u0000ed_change",
      {
        sampleCount: 0,
        leaves: [],
      },
    ],
  ]);

  const result = expandEventParameterRows(rows, sampled);

  assert.deepEqual(result[1].slice(0, 8), ["ResourceChange", "资源变化", "", "资源", "personal", "ed_change.WORLD_ZHU_GUO", "世界资源：朱果", "数值"]);
  assert.deepEqual(result[2].slice(0, 8), ["", "", "", "", "personal", "ed_change.WORLD_FU_MU", "世界资源：扶木", "数值"]);
  assert.equal(result[3][5], "ed_change");
  assert.match(result[3][8], /近 28 天未采样到 JSON 子字段/);
});
