# External IO — legacy evidence record

**Status:** retained evidence, not v3 specification.

The legacy runtime has governed external-IO commands for web search, HTTP/HTTPS download, checksum, gzip compression, and archive verification. Their wet-run output is evidence for the current implementation only.

In v3 these capabilities are tools executed inside a node work packet. Every external-IO action must additionally declare:

- node and parent scope;
- URL/network permission;
- destination path;
- maximum bytes and timeout;
- checksum/evidence requirement;
- sensitivity and data-egress classification;
- event and recovery correlation;
- user/provider/model context when a model is involved.

External IO never receives permission from RAG retrieval or CodeGraph. A node without explicit tool scope must be blocked.

## Historical command surface

| Command | Legacy purpose | v3 disposition |
|---|---|---|
| `web search` | governed search with evidence | retain as scoped node tool |
| `download` | download into workspace | retain with node scope and egress policy |
| `checksum` | hash workspace file | retain as evidence tool |
| `compress` | gzip workspace file | retain as scoped mutation |
| `archive verify` | verify gzip/archive | retain as evidence tool |

Detailed generated examples belong to test artifacts, not to product specification. The single implementation plan is [`../TODO.md`](../TODO.md).
