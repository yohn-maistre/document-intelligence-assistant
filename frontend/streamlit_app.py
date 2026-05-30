"""Streamlit stub — intentionally minimal.

We shipped Textual Studio as the operator surface (see
`src/klerk/studio/app.py` + `klerk-studio` script) instead of Streamlit.
This file is a *deliberate* leave-behind for reviewers who go looking
for a Streamlit entry point.

Why Textual instead of Streamlit:
  - Studio is reviewer-facing on local-only deploys; the brief asks for
    `docker compose up` to bring everything up, not for a web-facing
    Streamlit cloud. Textual ships as a TUI (`klerk-studio`) AND a
    browser deploy (`textual serve` ≥ 0.86) from the same single source
    file — no separate-venv hop for the browser path.
  - The five-panel layout (Chat / Corpus / Eval / Traces / Outputs)
    benefits from Textual's keyboard-first model: 1-5 jumps between
    panels, r reloads, q quits. Streamlit's reactive widget model would
    need a sidebar nav and would re-run the whole script per click.
  - Bloomberg-terminal feel is a deliberate signal — the corpus is the
    operator's surface for a corporate doc-intelligence tool, not a
    dashboard for end-users.

How to actually run klerk's UI:

    klerk-studio                       # TUI in your terminal
    klerk-studio --serve               # browser via `textual serve`

Or drive the API directly:

    uvicorn klerk.api.server:app --reload
    # then open http://localhost:8000/docs

If you genuinely need Streamlit, the shape it would take is sketched
below as comments. The actual implementation would be ~30 lines but
adds a UI surface that duplicates Studio without adding capability.

We deliberately do not ship a working Streamlit binary — leaving it
unbuilt is the honest signal that Textual is the chosen frontend.
"""

# ─── Sketch (not executed) ───────────────────────────────────────────────────
# import streamlit as st
# import httpx
# import json
#
# st.set_page_config(page_title="klerk", layout="wide")
# st.title("klerk — Document Intelligence Assistant")
#
# api_base = st.sidebar.text_input("API base", value="http://localhost:8000")
# locale = st.sidebar.radio("Locale", ["en", "id"], index=0)
#
# tabs = st.tabs(["Chat", "Corpus", "Eval", "Outputs"])
#
# with tabs[0]:
#     q = st.text_input("Question")
#     if st.button("Ask"):
#         # POST /chat (SSE) and stream the tokens into a placeholder
#         placeholder = st.empty()
#         buf = []
#         with httpx.stream(
#             "POST",
#             f"{api_base}/chat",
#             json={"query": q, "locale": locale},
#             timeout=120,
#         ) as r:
#             for line in r.iter_lines():
#                 if line.startswith("data: "):
#                     payload = json.loads(line[6:])
#                     if "text" in payload:
#                         buf.append(payload["text"])
#                         placeholder.markdown("".join(buf))
#                     elif "citations" in payload:
#                         st.caption(f"Citations: {payload['citations']}")
#
# # ... (Corpus / Eval / Outputs tabs would mirror Studio's read-out)


def main() -> None:
    raise SystemExit(
        "frontend/streamlit_app.py is a stub — klerk's UI is Textual Studio.\n"
        "  TUI:     klerk-studio\n"
        "  Browser: klerk-studio --serve\n"
        "See the comment block in this file for the rationale."
    )


if __name__ == "__main__":
    main()
