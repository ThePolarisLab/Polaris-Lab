import {
  EventErrorHandler,
  EventHandler,
  EventSubscription,
  IEvent,
} from "./IEvent";
import { IEventBus } from "./IEventBus";

export class EventBus implements IEventBus {
  private readonly handlers = new Map<string, Set<EventHandler>>();
  private readonly allHandlers = new Set<EventHandler>();

  constructor(private readonly onError?: EventErrorHandler) {}

  publish<TEvent extends IEvent>(event: TEvent): void {
    for (const handler of this.snapshot(event.name)) {
      try {
        const result = handler(event);
        if (result && typeof (result as Promise<void>).catch === "function") {
          void (result as Promise<void>).catch((error) => this.report(event, error));
        }
      } catch (error) {
        this.report(event, error);
      }
    }
  }

  async publishAsync<TEvent extends IEvent>(event: TEvent): Promise<void> {
    for (const handler of this.snapshot(event.name)) {
      try {
        await handler(event);
      } catch (error) {
        this.report(event, error);
      }
    }
  }

  subscribe<TEvent extends IEvent>(
    eventName: TEvent["name"],
    handler: EventHandler<TEvent>,
  ): EventSubscription {
    const handlers = this.handlers.get(eventName) ?? new Set<EventHandler>();
    handlers.add(handler as EventHandler);
    this.handlers.set(eventName, handlers);
    return () => {
      handlers.delete(handler as EventHandler);
      if (handlers.size === 0) {
        this.handlers.delete(eventName);
      }
    };
  }

  subscribeAll(handler: EventHandler): EventSubscription {
    this.allHandlers.add(handler);
    return () => this.allHandlers.delete(handler);
  }

  clear(eventName?: string): void {
    if (eventName === undefined) {
      this.handlers.clear();
      this.allHandlers.clear();
      return;
    }
    this.handlers.delete(eventName);
  }

  private snapshot(eventName: string): EventHandler[] {
    return [
      ...(this.handlers.get(eventName) ?? []),
      ...this.allHandlers,
    ];
  }

  private report(event: IEvent, error: unknown): void {
    this.onError?.({ event, error });
  }
}
