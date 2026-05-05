import { EventEmitter } from "events";
import Redis from "ioredis";
import { v4 as uuid } from "uuid";

interface DomainEvent {
  type: string;
  payload: unknown;
  timestamp: Date;
  correlationId: string;
}

const redis = new Redis(process.env.REDIS_URL!);

class EventBus {
  private emitter = new EventEmitter();

  async publish(event: DomainEvent): Promise<void> {
    await redis.lpush(`events:${event.type}`, JSON.stringify(event));
    this.emitter.emit(event.type, event);
  }

  subscribe(
    eventType: string,
    handler: (event: DomainEvent) => Promise<void>
  ): void {
    this.emitter.on(eventType, handler);
  }

  async replay(eventType: string, from: Date): Promise<void> {
    const events = await redis.lrange(`events:${eventType}`, 0, -1);
    for (const raw of events) {
      const event = JSON.parse(raw);
      if (new Date(event.timestamp) >= from) {
        this.emitter.emit(eventType, event);
      }
    }
  }
}

export const eventBus = new EventBus();

// Current usage:
eventBus.subscribe("user.created", async (event) => {
  const { userId } = event.payload as { userId: string };
  await sendWelcomeEmail(userId);
});

async function sendWelcomeEmail(userId: string) {
  // sends welcome email
}
