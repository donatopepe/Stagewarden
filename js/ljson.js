import { gzipSync, gunzipSync } from "node:zlib";

export const LJSON_VERSION = 1;

export function encode(records, options = {}) {
  const opts = {
    version: LJSON_VERSION,
    numericKeys: false,
    normalizeMissing: true,
    strictSchema: false,
    sortFields: false,
    ...options,
  };
  if (!Array.isArray(records)) {
    throw new TypeError("LJSON encode expects an array of objects.");
  }
  if (records.length === 0) {
    return { _version: opts.version, _fields: opts.numericKeys ? {} : [], data: [] };
  }
  const fields = collectFields(records, opts);
  if (opts.numericKeys) {
    const fieldMap = Object.fromEntries(fields.map((field, index) => [String(index + 1), field]));
    return {
      _version: opts.version,
      _fields: fieldMap,
      data: records.map((record) => encodeNumericRecord(record, fields, opts)),
    };
  }
  return {
    _version: opts.version,
    _fields: fields,
    data: records.map((record) => encodePositionalRecord(record, fields, opts)),
  };
}

export function decode(payload) {
  if (!payload || !Array.isArray(payload.data)) {
    throw new Error("LJSON payload missing valid data array.");
  }
  if (Array.isArray(payload._fields)) {
    const fields = payload._fields.map(String);
    return payload.data.map((row) => decodePositionalRecord(fields, row));
  }
  if (payload._fields && typeof payload._fields === "object") {
    const ordered = Array.from({ length: Object.keys(payload._fields).length }, (_v, i) => payload._fields[String(i + 1)]);
    return payload.data.map((row) => decodeNumericRecord(ordered, row));
  }
  throw new Error("LJSON payload missing valid _fields.");
}

export function encodeJsonBytes(records, { gzipEnabled = false, ...options } = {}) {
  const raw = Buffer.from(JSON.stringify(encode(records, options)));
  return gzipEnabled ? gzipSync(raw) : raw;
}

export function decodeJsonBytes(raw, { gzipped = false } = {}) {
  const bytes = gzipped ? gunzipSync(raw) : raw;
  return decode(JSON.parse(Buffer.from(bytes).toString("utf8")));
}

export function* streamEncode(records, { chunkSize = 100, ...options } = {}) {
  if (chunkSize <= 0) {
    throw new Error("chunkSize must be > 0");
  }
  let buffer = [];
  let chunk = 0;
  for (const record of records) {
    buffer.push(record);
    if (buffer.length === chunkSize) {
      chunk += 1;
      const payload = encode(buffer, options);
      payload._chunk = chunk;
      payload._chunk_size = buffer.length;
      payload._stream = true;
      yield payload;
      buffer = [];
    }
  }
  if (buffer.length > 0) {
    chunk += 1;
    const payload = encode(buffer, options);
    payload._chunk = chunk;
    payload._chunk_size = buffer.length;
    payload._stream = true;
    yield payload;
  }
}

export function* streamDecode(chunks) {
  for (const chunk of chunks) {
    for (const row of decode(chunk)) {
      yield row;
    }
  }
}

export function benchmarkSizes(records, { numericKeys = false, gzipEnabled = false } = {}) {
  const jsonRaw = Buffer.from(JSON.stringify(records));
  const ljsonRaw = encodeJsonBytes(records, { numericKeys });
  const jsonSize = gzipEnabled ? gzipSync(jsonRaw).length : jsonRaw.length;
  const ljsonSize = gzipEnabled ? gzipSync(ljsonRaw).length : ljsonRaw.length;
  const reductionPercent = jsonSize === 0 ? 0 : Number((((jsonSize - ljsonSize) / jsonSize) * 100).toFixed(2));
  return { json_size: jsonSize, ljson_size: ljsonSize, reduction_percent: reductionPercent, numeric_keys: numericKeys, gzip: gzipEnabled, record_count: records.length };
}

function collectFields(records, options) {
  if (!records.every((record) => record && typeof record === "object" && !Array.isArray(record))) {
    throw new TypeError("LJSON encode expects an array of plain objects.");
  }
  const fields = [...Object.keys(records[0])];
  const seen = new Set(fields);
  for (const record of records.slice(1)) {
    if (options.strictSchema && JSON.stringify(Object.keys(record)) !== JSON.stringify(fields)) {
      throw new Error("Record schema mismatch in strict mode.");
    }
    for (const key of Object.keys(record)) {
      if (!seen.has(key)) {
        seen.add(key);
        fields.push(key);
      }
    }
  }
  if (options.sortFields) {
    fields.sort();
  }
  return fields;
}

function encodePositionalRecord(record, fields, options) {
  return fields.map((field) => {
    if (Object.hasOwn(record, field)) return record[field];
    if (options.normalizeMissing) return null;
    throw new Error(`Missing field '${field}' in record.`);
  });
}

function encodeNumericRecord(record, fields, options) {
  const row = {};
  fields.forEach((field, index) => {
    if (Object.hasOwn(record, field)) row[String(index + 1)] = record[field];
    else if (options.normalizeMissing) row[String(index + 1)] = null;
    else throw new Error(`Missing field '${field}' in record.`);
  });
  return row;
}

function decodePositionalRecord(fields, row) {
  if (!Array.isArray(row)) throw new Error("Positional row must be an array.");
  const out = {};
  fields.forEach((field, index) => {
    out[field] = index < row.length ? row[index] : null;
  });
  return out;
}

function decodeNumericRecord(fields, row) {
  if (!row || typeof row !== "object" || Array.isArray(row)) throw new Error("Numeric row must be an object.");
  const out = {};
  fields.forEach((field, index) => {
    out[field] = Object.hasOwn(row, String(index + 1)) ? row[String(index + 1)] : null;
  });
  return out;
}
