export interface OutlookFolder {
  readonly id: string;
  readonly displayName: string;
  readonly parentFolderId?: string;
}

export interface OutlookAttachmentMetadata {
  readonly id: string;
  readonly name: string;
  readonly contentType?: string;
  readonly size?: number;
  readonly isInline?: boolean;
}

export interface OutlookMessage {
  readonly id: string;
  readonly subject?: string;
  readonly bodyPreview?: string;
  readonly body?: string;
  readonly bodyContentType?: "text" | "html";
  readonly from?: string;
  readonly toRecipients: readonly string[];
  readonly ccRecipients: readonly string[];
  readonly receivedAt?: string;
  readonly sentAt?: string;
  readonly internetMessageId?: string;
  readonly folderId?: string;
  readonly webLink?: string;
  readonly hasAttachments: boolean;
  readonly attachments: readonly OutlookAttachmentMetadata[];
}

export interface OutlookDeltaPage {
  readonly messages: readonly OutlookMessage[];
  readonly nextLink?: string;
  readonly deltaLink?: string;
}

export interface GraphMailClient {
  authenticate(credentialReference?: string, signal?: AbortSignal): Promise<void>;
  listFolders(signal?: AbortSignal): Promise<readonly OutlookFolder[]>;
  listMessagesDelta(cursor?: string, limit?: number, signal?: AbortSignal): Promise<OutlookDeltaPage>;
  disconnect(): Promise<void>;
}
