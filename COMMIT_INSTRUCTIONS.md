# Commit Instructions

## Store in Polaris

Start the Polaris server, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\store_foundation_memories.ps1
```

Verify with `GET /api/v1/memories` in Swagger.

## GitHub Desktop

Copy these files into the repository:

- `docs/foundation/POL-FOUND-002-builder-principles.md`
- `scripts/store_foundation_memories.ps1`

Commit summary:

```text
docs(foundation): preserve the Builder principles
```

Description:

```text
- Adopt "Every Builder matters" as an official Polaris principle
- Add the permanent foundation dedication
- Document the Builder test
- Add a script to store both principles in Polaris memory
```

Click **Commit to main**, then **Push origin**.
