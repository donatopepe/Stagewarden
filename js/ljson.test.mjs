import test from "node:test";
import assert from "node:assert/strict";

import { benchmarkSizes, decode, decodeJsonBytes, encode, encodeJsonBytes, streamDecode, streamEncode } from "./ljson.js";

test("roundtrip positional", () => {
  const records = [
    { id: 1, name: "Mario", meta: { city: "Rome" } },
    { id: 2, name: "Luigi", meta: { city: "Milan" } },
  ];
  assert.deepEqual(decode(encode(records)), records);
});

test("roundtrip numeric keys", () => {
  const records = [{ id: 1, name: "Mario" }, { id: 2, name: "Luigi" }];
  assert.deepEqual(decode(encode(records, { numericKeys: true })), records);
});

test("gzip bytes roundtrip", () => {
  const records = Array.from({ length: 10 }, (_v, index) => ({ id: index, name: `user-${index}` }));
  assert.deepEqual(decodeJsonBytes(encodeJsonBytes(records, { gzipEnabled: true }), { gzipped: true }), records);
});

test("stream roundtrip", () => {
  const records = Array.from({ length: 7 }, (_v, index) => ({ id: index, name: `user-${index}` }));
  const chunks = [...streamEncode(records, { chunkSize: 3 })];
  assert.deepEqual([...streamDecode(chunks)], records);
});

test("benchmark reduction positive on larger dataset", () => {
  const records = Array.from({ length: 200 }, (_v, index) => ({ id: index, name: `user-${index}`, role: "member" }));
  const bench = benchmarkSizes(records);
  assert.ok(bench.reduction_percent > 0);
});
