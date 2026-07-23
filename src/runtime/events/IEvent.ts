export interface IEvent {
  readonly id: string;
  readonly name: string;
  readonly timestamp: Date;
}

export type EventHandler<TEvent extends IEvent = IEvent> =
  (event: TEvent) => void | Promise<void>;

export type EventSubscription = () => void;

export interface EventDispatchError {
  readonly event: IEvent;
  readonly error: unknown;
}

export type EventErrorHandler = (failure: EventDispatchError) => void;
