/**
 * pi-runtime.ts — launches the chat REPL with Pi as a hidden dependency.
 *
 * Pi (@mariozechner/pi-coding-agent) provides the flicker-free diff-rendered
 * TUI we don't want to rebuild. We invoke it via subprocess with klerk's
 * config: system prompt, MCP server pointing at klerk-mcp, and a custom
 * theme. The user never sees the name "Pi" in any visible string.
 *
 * If Pi isn't installed (e.g. published klerk-cli is used standalone), we
 * fall back to a clear message rather than crashing — the gateway path
 * (klerk-mcp + Claude Desktop / Goose / Cursor) is the production answer.
 */

import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import chalk from "chalk";

const KLERK_SYSTEM_PROMPT = `\
You are klerk, a document intelligence agent. You answer questions and produce
work over the user's document corpus by calling klerk's tools (search_hybrid,
read_chunk, propose, faq_build, contradict_scan, extract_kg).

Always ground factual claims in retrieved chunks and cite using
[doc_id:chunk_idx]. Match the user's language (English ↔ Bahasa). If retrieved
evidence is insufficient, say so explicitly and propose what additional
retrieval would help — do not fabricate.
`;

interface ChatOptions {
  locale: "en" | "id";
}

function parseArgs(args: string[]): ChatOptions {
  let locale: "en" | "id" = "en";
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if ((a === "--locale" || a === "-l") && args[i + 1]) {
      const v = args[i + 1];
      if (v === "id" || v === "en") locale = v;
      i++;
    }
  }
  return { locale };
}

function locatePiBinary(): string | null {
  // 1) sibling node_modules (monorepo dev install)
  const here = dirname(fileURLToPath(import.meta.url));
  const candidates = [
    resolve(here, "../../node_modules/.bin/pi"),
    resolve(here, "../../../node_modules/.bin/pi"),
    resolve(here, "../../../../node_modules/.bin/pi"),
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return null;
}

export async function runChat(args: string[]): Promise<void> {
  const { locale } = parseArgs(args);

  console.log(chalk.dim("  locale: ") + chalk.cyan(locale));
  console.log(chalk.dim("  starting klerk chat...\n"));

  const piBin = locatePiBinary();
  if (!piBin) {
    console.log(
      chalk.yellow("  klerk chat needs the underlying runtime installed. ") +
        chalk.dim("Run ") + chalk.cyan("pnpm install") + chalk.dim(" in the repo root, then try again.")
    );
    console.log(
      chalk.dim("  For agent-to-agent access (Claude Desktop / Goose / Cursor), point an MCP client at ") +
        chalk.cyan("klerk-mcp") + chalk.dim(" — that path doesn't need this binary.")
    );
    process.exitCode = 3;
    return;
  }

  // Delegate the chat loop. KLERK_* env vars carry our system prompt and
  // locale into the runtime; the runtime spawns klerk-mcp as its MCP server
  // so all of klerk's tools are reachable from the chat prompt.
  const env = {
    ...process.env,
    KLERK_SYSTEM_PROMPT,
    KLERK_LOCALE: locale,
    KLERK_MCP_COMMAND: "klerk-mcp",
  };

  const child = spawn(piBin, [], { stdio: "inherit", env });
  await new Promise<void>((res) => {
    child.on("exit", () => res());
    child.on("error", (err) => {
      console.error(chalk.red("  klerk chat: runtime error — "), err.message);
      res();
    });
  });
}
