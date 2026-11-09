# Copied from mcp_coder src/mcp_coder/llm/providers/langchain/_product.py at commit f88e6b55 (MarcusJellinghaus/mcp_coder#1400).
"""Product-specific user-facing texts of the LangChain model layer.

The only model-layer module a downstream copy (agent-workbench) replaces.
Keep every other model-layer module free of product names.
"""

INSTALL_HINT = "Install with: pip install 'agent-workbench[langchain]'"
OLLAMA_INSTALL_HINT = "Install with: pip install 'agent-workbench[langchain-ollama]'"
CONFIG_SECTION = "[llm]"
PRODUCT_NAME = "agent-workbench"
