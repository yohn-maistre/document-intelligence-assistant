/**
 * pi-extension-klerk — klerk's skills + tool descriptors, packaged for Pi.
 *
 * Install in any Pi instance to gain klerk's document-intelligence verbs
 * without running the klerk-cli shell. The extension registers six skills
 * and points Pi at klerk-mcp (which exposes the real Python implementations).
 *
 * Usage:
 *   import { registerKlerkExtension } from "@yohnmaistre/pi-extension-klerk";
 *   registerKlerkExtension(pi, { mcpServer: "klerk-mcp" });
 *
 * The skills below are loaded into Pi's system prompt at startup; the tools
 * are resolved at call time via the MCP server. We do NOT inline the Python
 * tool logic into TypeScript — that would re-implement klerk twice. The
 * extension is the wiring; klerk-mcp is the implementation.
 */

export const KLERK_EXTENSION_VERSION = "0.0.1";

export interface KlerkExtensionConfig {
  /** Command to launch klerk-mcp. Default: `klerk-mcp` (must be in PATH). */
  mcpServer?: string;
  /** Default locale (en | id) the extension passes to klerk tools. */
  locale?: "en" | "id";
  /** Override the system-prompt addition. Defaults to klerk's canonical prompt. */
  systemPromptOverride?: string;
}

export interface KlerkSkill {
  name: string;
  description: string;
  body: string;
}

export const KLERK_SKILLS: KlerkSkill[] = [
  {
    name: "corpus",
    description: "How to navigate klerk's indexed corpus.",
    body:
      "Use search_hybrid for relevant passages, list_docs to enumerate sources, " +
      "and read_chunk to fetch a specific chunk by id. Cite using [doc_id:chunk_idx].",
  },
  {
    name: "propose",
    description: "When and how to use the adversarial proposal pipeline.",
    body:
      "For multi-section drafts (briefs, reports, RFP responses), call `propose` " +
      "with a topic + section count. Pipeline: Scope → Drafter-A ‖ Drafter-B → " +
      "Citation Tracer → Adjudicator → Critic. The returned markdown includes " +
      "the winning sections and the 5-axis rubric.",
  },
  {
    name: "contradict",
    description: "Surface inconsistencies across the corpus.",
    body:
      "Call `contradict_scan` to find statements about the same entity that " +
      "disagree across chunks. Output is a Markdown report with chunk citations.",
  },
  {
    name: "faq",
    description: "Auto-generate an FAQ from the corpus.",
    body:
      "Call `faq_build` to have klerk propose its own questions per doc and " +
      "answer them with citations. Use this for onboarding decks and " +
      "self-service knowledge bases.",
  },
  {
    name: "kg",
    description: "Inspect the knowledge graph.",
    body:
      "Use `extract_kg` to extract entities + relations from arbitrary text, " +
      "and `kg_stats` to size the current graph. The graph is persisted under " +
      "data/kg/graph.json and reused across runs.",
  },
  {
    name: "eval",
    description: "Run the eval rubric.",
    body:
      "Call `eval_run_rubric` to score klerk against the golden Q&A set. " +
      "Five axes: retrieval_recall, substring_coverage, citation_grounded, " +
      "locale_match, confidence. Mean is reported alongside per-locale " +
      "breakdown for Bahasa parity.",
  },
];

export const KLERK_SYSTEM_PROMPT = `\
You are klerk, a document intelligence agent. Ground every factual claim in
retrieved chunks and cite using [doc_id:chunk_idx]. Match the user's language
(English ↔ Bahasa Indonesia). If retrieved evidence is insufficient, say so
and propose what additional retrieval would help — do not fabricate.
`;

/**
 * Register the klerk extension with a Pi instance.
 *
 * The Pi API surface (`piInstance.registerSkill`, `piInstance.addMcpServer`)
 * may differ across Pi versions. This function is intentionally lenient: it
 * tries the documented API, and falls back to populating an `__klerk` slot
 * on the instance for older versions. The Pi maintainer (Mario Zechner) can
 * adapt as Pi's extension surface stabilises.
 */
export function registerKlerkExtension(
  piInstance: unknown,
  config: KlerkExtensionConfig = {}
): void {
  const cfg = {
    mcpServer: config.mcpServer ?? "klerk-mcp",
    locale: config.locale ?? "en",
    systemPromptOverride: config.systemPromptOverride ?? KLERK_SYSTEM_PROMPT,
  };

  const instance = piInstance as Record<string, unknown>;

  // Try the documented Pi extension hooks first
  const registerSkill = instance.registerSkill as
    | ((skill: KlerkSkill) => void)
    | undefined;
  const addMcpServer = instance.addMcpServer as
    | ((name: string, command: string) => void)
    | undefined;
  const appendSystemPrompt = instance.appendSystemPrompt as
    | ((text: string) => void)
    | undefined;

  if (registerSkill) {
    for (const skill of KLERK_SKILLS) registerSkill(skill);
  } else {
    instance.__klerk_skills = KLERK_SKILLS;
  }

  if (addMcpServer) {
    addMcpServer("klerk", cfg.mcpServer);
  } else {
    instance.__klerk_mcp = cfg.mcpServer;
  }

  if (appendSystemPrompt) {
    appendSystemPrompt(cfg.systemPromptOverride);
  } else {
    instance.__klerk_system_prompt = cfg.systemPromptOverride;
  }

  instance.__klerk_config = cfg;
}

export default registerKlerkExtension;
