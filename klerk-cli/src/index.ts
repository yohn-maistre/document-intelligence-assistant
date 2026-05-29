/**
 * klerk-cli entry — Ink-wrapped shell that hides Pi.
 *
 * Wired in h19.5–22. Until then this just prints a branded banner so the
 * binary is callable and the npm install is provable end-to-end.
 */

import chalk from "chalk";

function banner(): void {
  const lines = [
    "",
    chalk.cyan("  ╔═══════════════════════════════════════════╗"),
    chalk.cyan("  ║") + chalk.bold.white("              k l e r k                    ") + chalk.cyan("║"),
    chalk.cyan("  ║") + chalk.dim("       document intelligence agent         ") + chalk.cyan("║"),
    chalk.cyan("  ╚═══════════════════════════════════════════╝"),
    "",
    chalk.dim("  v0.0.1 · type ") + chalk.bold("klerk --help") + chalk.dim(" for verbs"),
    "",
  ];
  for (const l of lines) console.log(l);
}

function main(): void {
  banner();
  const argv = process.argv.slice(2);
  if (argv.length === 0 || argv[0] === "--help" || argv[0] === "-h") {
    console.log(chalk.bold("  Surfaces:"));
    console.log("    " + chalk.cyan("klerk chat") + chalk.dim("           open the chat shell (h19.5–22)"));
    console.log("    " + chalk.cyan("klerk ask <q>") + chalk.dim("        one-shot Q&A over the corpus"));
    console.log("    " + chalk.cyan("klerk propose <topic>") + chalk.dim(" adversarial proposal pipeline"));
    console.log("    " + chalk.cyan("klerk-mcp") + chalk.dim("            MCP gateway for other agents"));
    console.log("    " + chalk.cyan("klerk-studio") + chalk.dim("         Textual operator TUI"));
    console.log("");
    console.log(chalk.dim("  Python verbs: ") + chalk.bold("uv run klerk --help"));
    return;
  }

  // h19.5–22: branch on argv[0] === "chat" → boot the Ink shell + delegate to Pi
  console.log(chalk.yellow("  klerk-cli shell is wired in h19.5–22."));
  console.log(chalk.dim("  Use ") + chalk.cyan("uv run klerk " + argv.join(" ")) + chalk.dim(" for now."));
}

main();
