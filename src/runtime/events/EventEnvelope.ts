import { IEvent } from "./IEvent";

export interface EventMetadata {
  readonly correlationId?: string;
  readonly causationId?: string;
  readonly source?: string;
  readonly version?: number;
}

export interface EventEnvelope<TEvent extends IEvent = IEvent> {
  readonly event: TEvent;
  readonly metadata: Readonly<EventMetadata>;
}

export function envelope<TEvent extends IEvent>(
  event: TEvent,
  metadata: EventMetadata = {},
): EventEnvelope<TEvent> {
  return {
    event,
    metadata: { ...metadata },
  };
}
