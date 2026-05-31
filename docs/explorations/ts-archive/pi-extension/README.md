# @yohnmaistre/pi-extension-klerk

klerk's skills + tool descriptors as a Pi extension. Install this in any Pi instance to gain klerk's document-intelligence verbs without running the full `klerk-cli` shell.

## What it does

Registers six skills (`corpus`, `propose`, `contradict`, `faq`, `kg`, `eval`) and points Pi at `klerk-mcp` (the MCP server in the klerk Python package). Pi then has the full klerk tool surface available from any chat prompt.

## Install

```sh
npm install @yohnmaistre/pi-extension-klerk @mariozechner/pi-coding-agent
```

You also need `klerk-mcp` on your PATH:

```sh
uv pip install klerk            # or: pipx install klerk
# `klerk-mcp` is now exposed as a console script.
```

## Use

```ts
import { registerKlerkExtension } from "@yohnmaistre/pi-extension-klerk";

const pi = createPiInstance(); // however your Pi setup creates it
registerKlerkExtension(pi, {
  mcpServer: "klerk-mcp",  // default
  locale: "id",            // optional; defaults to "en"
});
```

## What you get

Inside any Pi chat, the agent can now answer prompts like:

- *"What does the Q1 memo say about consultant rate overruns?"* → uses `search_hybrid` + cites `[memo_internal_q1:1]`
- *"Draft a 3-section project brief on Pelangi's IP-clause renegotiation"* → uses `propose` and returns the adjudicated, rubric-scored markdown
- *"Find any contradictions across the corpus"* → uses `contradict_scan` and returns the report
- *"Build an FAQ for the HR policy"* → uses `faq_build`

## Architecture

The extension is *wiring*, not implementation. The Python `klerk-mcp` server is where the actual retrieval, KG extraction, adversarial pipeline, etc. live. This split means:

- Bugs and improvements ship in one place (the Python package)
- Pi extension stays small (~150 LOC, just descriptors + system prompt)
- Same skills work for Claude Desktop, Goose, Cursor — all via the same `klerk-mcp` server

See [github.com/yohn-maistre/document-intelligence-assistant](https://github.com/yohn-maistre/document-intelligence-assistant) for the full klerk codebase and architecture docs.

## License

MIT. Same as klerk and Pi.
