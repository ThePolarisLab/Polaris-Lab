# Outlook Read-Only Permission Boundary

Status: Track 4B implementation

Polaris uses Microsoft Graph delegated OAuth for Outlook. The connector is not a mail client and must not request or exercise mail mutation authority.

## Requested Scopes

```text
openid profile email offline_access https://graph.microsoft.com/Mail.Read
```

Purpose:

- `openid profile email`: identify the signed-in Microsoft account during OAuth.
- `offline_access`: allow Polaris to maintain a tenant-bound encrypted refresh token.
- `https://graph.microsoft.com/Mail.Read`: read mailbox folders, message metadata/body text, and attachment metadata.

## Forbidden Scopes

Do not add:

- `Mail.ReadWrite`
- `Mail.Send`
- mailbox rule permissions
- calendar permissions
- contacts permissions
- Teams permissions
- application-wide mailbox permissions unless a later governance review explicitly approves them

The runtime rejects configured scopes containing `Mail.ReadWrite` or `Mail.Send`.

## Data Boundary

Polaris reads from the connected mailbox and writes only to Polaris-owned Outlook tables:

- `outlook_oauth_credentials`
- `outlook_oauth_states`
- `outlook_folders`
- `outlook_folder_checkpoints`
- `outlook_messages`
- `outlook_attachments`
- `outlook_message_classifications`
- `outlook_sync_history`

The connector does not write into QuickBooks, Motive, or Microsoft provider-owned tables.

## Mutation Prohibition

Track 4B does not implement:

- send
- reply
- forward
- delete
- move
- mark read/unread
- flag changes
- category edits
- draft creation
- rule changes
- automatic responses

Any future mutation requires a separate governed workstream, new permissions, threat model, tests, and human approval.
