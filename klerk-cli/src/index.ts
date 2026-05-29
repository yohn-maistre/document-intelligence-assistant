/**
 * klerk-cli — the TS shell that owns klerk's chat surface.
 *
 * Architecture: this shell holds the brand identity (banner, copy, help
 * screens). The actual chat experience delegates to a runtime that hides
 * Pi entirely; users never see the name "Pi" in any visible string.
 *
 * Wired in this file:
 *   klerk            → banner + help (default)
 *   klerk --help     → help
 *   klerk --version  → version
 *   klerk chat       → launch the chat REPL (Pi-runtime, hidden)
 *
 * Everything else (verbs like `ask`, `propose`, `index build`) lives in the
 * Python CLI installed via `uv` and exposed as `klerk` there. The README
 * spells this out: TS `klerk` for chat; `uv run klerk <verb>` for verbs.
 */

import chalk from "chalk";

const VERSION = "0.0.1";
const TAGLINE = "document intelligence agent";

function banner(): void {
  const w = 49;
  const top    = chalk.cyan("  ╔" + "═".repeat(w - 4) + "╗");
  const bot    = chalk.cyan("  ╚" + "═".repeat(w - 4) + "╝");
  const pad = (s: string): string => {
    const visible = s.length;
    const slack = w - 4 - visible;
    const left = Math.floor(slack / 2);
    const right = slack - left;
    return " ".repeat(left) + s + " ".repeat(right);
  };

  console.log();
  console.log(top);
  console.log(chalk.cyan("  ║") + chalk.bold.white(pad("k l e r k")) + chalk.cyan("║"));
  console.log(chalk.cyan("  ║") + chalk.dim(pad(TAGLINE)) + chalk.cyan("║"));
  console.log(bot);
  console.log();
  console.log(chalk.dim("  v" + VERSION + " · ") + chalk.bold("klerk --help") + chalk.dim(" for the surfaces"));
  console.log();
}

function help(): void {
  banner();
  console.log(chalk.bold("  CHAT (this binary):"));
  console.log("    " + chalk.cyan("klerk chat") + chalk.dim("                  interactive Q&A REPL"));
  console.log("    " + chalk.cyan("klerk chat --locale id") + chalk.dim("       route Bahasa queries through Qwen3"));
  console.log();
  console.log(chalk.bold("  VERBS (Python CLI):"));
  console.log("    " + chalk.cyan("uv run klerk ask \"...\"") + chalk.dim("      one-shot Q&A with citations"));
  console.log("    " + chalk.cyan("uv run klerk propose \"...\"") + chalk.dim("  adversarial proposal pipeline"));
  console.log("    " + chalk.cyan("uv run klerk index build") + chalk.dim("    parse → chunk → embed → upsert"));
  console.log("    " + chalk.cyan("uv run klerk kg extract") + chalk.dim("     entity + relation extraction"));
  console.log("    " + chalk.cyan("uv run klerk contradict scan") + chalk.dim(" KG contradiction sweep"));
  console.log("    " + chalk.cyan("uv run klerk faq build") + chalk.dim("      Corpus Learning Agent → FAQ"));
  console.log("    " + chalk.cyan("uv run klerk eval run") + chalk.dim("       RAGAS + rubric + Bahasa parity"));
  console.log();
  console.log(chalk.bold("  GATEWAYS:"));
  console.log("    " + chalk.cyan("uv run klerk-mcp") + chalk.dim("            MCP server (stdio) for other agents"));
  console.log("    " + chalk.cyan("uv run klerk-studio") + chalk.dim("          Textual operator TUI"));
  console.log();
  console.log(chalk.dim("  docs: README.md · docs/architecture.md · docs/design-decisions.md"));
  console.log();
}

function version(): void {
  console.log("klerk " + VERSION);
}

async function chat(args: string[]): Promise<void> {
  banner();
  const { runChat } = await import("./chat/pi-runtime.js");
  await runChat(args);
}

async function main(): Promise<void> {
  const argv = process.argv.slice(2);
  const first = argv[0];

  if (!first || first === "--help" || first === "-h" || first === "help") {
    help();
    return;
  }
  if (first === "--version" || first === "-v" || first === "version") {
    version();
    return;
  }
  if (first === "chat") {
    await chat(argv.slice(1));
    return;
  }

  // Unknown verb — guide the user toward the Python CLI
  banner();
  console.log(chalk.yellow("  Unknown verb: ") + chalk.bold(first));
  console.log(chalk.dim("  This binary owns the chat surface only."));
  console.log(chalk.dim("  Try ") + chalk.cyan("klerk --help") + chalk.dim(" or ") + chalk.cyan(`uv run klerk ${argv.join(" ")}`) + chalk.dim("."));
  process.exitCode = 2;
}

main().catch((err) => {
  console.error(chalk.red("klerk: ") + (err instanceof Error ? err.message : String(err)));
  process.exitCode = 1;
});
