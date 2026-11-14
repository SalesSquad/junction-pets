#!/usr/bin/env python3
"""Add only Meta's public documentation MCP to this Codex invocation."""
import os
import sys

os.execvp("codex", [
    "codex",
    "-c", 'mcp_servers.meta_wearables_docs.url="https://mcp.developer.meta.com/wearables"',
    "-c", 'mcp_servers.meta_wearables_docs.enabled_tools=["search_dat_docs","search_webapps_docs"]',
    *sys.argv[1:],
])
