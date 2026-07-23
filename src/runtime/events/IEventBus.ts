import { EventHandler, EventSubscription, IEvent } from "./IEvent";

export interface IEventBus {
  publish<TEvent extends IEvent>(event: TEvent): void;
  publishAsync<TEvent extends IEvent>(event: TEvent): Promise<void>;
  subscribe<TEvent extends IEvent>(
    eventName: TEvent["name"],
    handler: EventHandler<TEvent>,
  ): EventSubscription;
  subscribeAll(handler: EventHandler): EventSubscription;
  clear(eventName?: string): void;
}
