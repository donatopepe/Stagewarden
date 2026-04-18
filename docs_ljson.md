# LJSON

`LJSON` (Lightweight JSON) serializza array di oggetti omogenei riducendo la ridondanza delle chiavi.

## Formati supportati

Formato posizionale:

```json
{
  "_version": 1,
  "_fields": ["id", "name"],
  "data": [
    [1, "Mario"],
    [2, "Luigi"]
  ]
}
```

Formato con chiavi numeriche:

```json
{
  "_version": 1,
  "_fields": {
    "1": "id",
    "2": "name"
  },
  "data": [
    {"1": 1, "2": "Mario"},
    {"1": 2, "2": "Luigi"}
  ]
}
```

## API

- `encode(records, options=None)`
- `decode(payload)`
- `encode_json_bytes(records, gzip_enabled=False)`
- `decode_json_bytes(raw, gzipped=False)`
- `dump_file(path, records, ...)`
- `load_file(path, ...)`
- `stream_encode(records, chunk_size=100)`
- `stream_decode(chunks)`
- `benchmark_sizes(records, numeric_keys=False, gzip_enabled=False)`

## Proprietà

- `decode(encode(x)) == x` per record JSON object-based
- campi mancanti normalizzati a `null`
- ordine dei campi preservato
- complessità lineare rispetto al numero di record
- supporto a valori annidati JSON come valore di campo

## Limiti e trade-off

- la compressione funziona bene su dataset con molte righe e schema stabile
- su dataset piccoli il vantaggio può essere minimo
- LJSON comprime solo la ridondanza delle chiavi top-level, non i valori
- la modalità streaming produce chunk JSON validi, non un singolo documento unico continuo
- in `strict_schema=True` gli oggetti devono avere schema identico e stesso ordine chiavi

## Uso predefinito nel progetto

L’agente usa LJSON di default per:

- persistenza dei tentativi in `MemoryStore`
- snapshot di simulazione dell’`Executor`
- trace del loop agente in `.agent_cli_trace.ljson`
- benchmark dimensione vs JSON standard

## CLI

```bash
agent-cli --ljson-encode records.json
agent-cli --ljson-encode records.json --ljson-numeric --ljson-output records.ljson
agent-cli --ljson-decode records.ljson
agent-cli --ljson-benchmark records.json
```

## JavaScript

Porta Node.js disponibile in:

- [js/ljson.js](/Users/donato/js/ljson.js)
- [js/ljson.test.mjs](/Users/donato/js/ljson.test.mjs)

Test:

```bash
node --test /Users/donato/js/ljson.test.mjs
```
