# PGE-002 — Repository Intelligence

## Status

Implemented for review.

## Purpose

PGE-002 extends the Polaris GitHub Engine with safe, read-oriented repository discovery. It provides the factual repository context required by later code-understanding, review, and refactoring capabilities.

## Capabilities

- Repository metadata
- Branch discovery inherited from PGE-001
- Recursive or non-recursive repository tree retrieval
- UTF-8 text file reading with a 1 MB safety limit
- Repository-scoped GitHub code search
- Commit history by branch and optional path

## API

All routes use the existing `/api/v1/github` prefix.

| Method | Route | Purpose |
|---|---|---|
| GET | `/repository` | Return selected repository metadata |
| GET | `/tree` | Return the Git tree for a ref |
| GET | `/files/read` | Read one UTF-8 text file |
| GET | `/search` | Search code within the allowlisted repository |
| GET | `/commits` | Return commit history for a ref and optional path |

PGE-001 write routes remain available and continue to require `POLARIS_GITHUB_WRITE_ENABLED=true`.

## Security boundaries

- The repository remains restricted to `ThePolarisLab/Polaris-Lab`.
- Repository paths reject `..` traversal.
- File reads accept only UTF-8 text returned through GitHub's base64 content API.
- File reads are capped at 1,000,000 bytes.
- Search is always scoped to the allowlisted repository.
- Query limits are constrained to 1–100 results.
- Read capabilities do not require write mode.

## Configuration

- `POLARIS_GITHUB_TOKEN` — required GitHub token.
- `POLARIS_GITHUB_REPOSITORY` — optional, but must match the allowlisted repository.
- `POLARIS_GITHUB_WRITE_ENABLED` — controls only write operations.

## Verification

Unit tests cover:

- write-mode enforcement;
- repository allowlisting;
- path traversal rejection;
- tree ref encoding;
- UTF-8 file decoding;
- repository-scoped search;
- commit result limit enforcement.

## Future work

PGE-003 may build symbol extraction, dependency mapping, language-aware parsing, and indexed local search on top of these interfaces. Those capabilities are deliberately outside PGE-002.
