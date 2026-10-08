# Graphify workflow inspection

Checkpoint: 2026-10-08. Development tooling only; application dependencies and financial records are unchanged.

## Installation

[Graphify upstream](https://github.com/Graphify-Labs/graphify) supplies the CLI and Codex skill. This project pins `graphifyy[sql]==0.9.77` in an isolated environment. From the repository root on Windows:

```powershell
python -m venv .runtime/graphify-venv
.runtime/graphify-venv/Scripts/python.exe -m pip install "graphifyy[sql]==0.9.77"
```

The upstream Codex skill and references are checked in under `.codex/skills/graphify/`. The project policy in AGENTS.md narrows the upstream semantic pipeline to code-only extraction. The upstream Codex hook is an intentional no-op; it is omitted here to avoid a PATH-dependent process on each tool call. No global PATH, cloud service, application dependency or background watcher is required.

## Workflow

```powershell
# Refresh after a code checkpoint, then generate the local report and HTML.
./scripts/graphify.ps1 extract . --code-only --max-workers 2
./scripts/graphify.ps1 cluster-only .

# Retrieve bounded context before reading relevant source.
./scripts/graphify.ps1 query "document extraction queue duplicate review inventory reconciliation" --budget 1500
./scripts/graphify.ps1 path "process_one" "ExtractionQueue"
./scripts/graphify.ps1 explain "ExtractionQueue"
```

Use `/graphify` with the project skill, or these explicit PowerShell commands. The wrapper resolves the repository root even when called from another working directory and propagates the CLI exit status. Generated `graphify-out/graph.html`, `GRAPH_REPORT.md`, and `graph.json` remain local and ignored by Git.

`.graphifyignore` excludes runtime directories, credentials, data, samples, run evidence, benchmark data and skill files. Code-only extraction performs local AST parsing without a semantic model pass. SQL parsing uses the optional SQL grammar. Do not attach live database credentials or use a semantic backend by default. Reports may retain generic community labels without a configured model.

## Meaning and limits

The graph helps inspect the code paths for document upload, extraction leases, imports, duplicate decisions and reconciliation. It does not monitor running jobs or prove financial correctness. Use the existing authenticated document-job API and audit records for operational status. Refresh at checkpoints; no scheduled/background monitoring is enabled.

A query budget is an approximate output-context limit, not a guarantee about total conversation tokens. Truncated queries may omit the needed node: narrow the question or inspect a specific symbol before increasing the budget. Token savings have not been measured. Inferred links need confirmation in source and tests; missing graph symbols require targeted search.

## Verification

- Code-only extraction completed with 530 nodes, 1,566 edges and 26 communities.
- The 1,500-token workflow query returned queue, import, duplicate and reconciliation symbols and explicitly reported truncation.
- The path query returned `process_one() --uses [INFERRED]--> ExtractionQueue`; the worker source confirms the queue argument/type and method calls.
- Report and HTML generation completed without a configured model backend.
- Extraction reported seven code files without symbols, including the Marimo notebook and a policy-only SQL migration. This is partial static analysis, not complete coverage.
- The application test suite was not rerun for this tooling-only change. The preceding application checkpoint passed 108 tests with one real OCR fixture test skipped.
