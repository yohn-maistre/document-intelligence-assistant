/**
 * pi-extension-klerk — klerk's skills + tool descriptors as a Pi extension.
 *
 * Wired in h22–24. Until then this exports a placeholder so the npm package
 * is buildable and publishable.
 *
 * The extension registers:
 *   - skills:  corpus / propose / contradict / faq / adversarial / anomaly
 *   - tools:   MCP tool descriptors pointing at the klerk-mcp server
 */

export const KLERK_EXTENSION_VERSION = "0.0.1";

export interface KlerkExtensionConfig {
  /** URL of the klerk-mcp server (stdio: `klerk-mcp`, http: `http://localhost:8000`). */
  mcpServer?: string;
  /** Default locale for the agent's tool calls. */
  locale?: "en" | "id";
}

export function registerKlerkExtension(_config: KlerkExtensionConfig = {}): void {
  // h22–24: register skills + tool descriptors with the Pi instance.
  // Stub for now so the package is publishable.
  void 0;
}

export default registerKlerkExtension;
