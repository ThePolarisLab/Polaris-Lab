import { MemoryRepository } from "./MemoryRepository";
import {
  DecisionMemoryInput,
  ExecutiveMemorySnapshot,
  MemoryMatch,
  MemoryQuery,
  MemoryRecord,
} from "./types";

const DAY_MS = 24 * 60 * 60 * 1000;

export class ExecutiveMemory {
  constructor(private readonly repository: MemoryRepository) {}

  async rememberDecision(input: DecisionMemoryInput): Promise<MemoryRecord> {
    const { request, decision } = input;
    const now = new Date();
    const record: MemoryRecord = {
      id: `decision:${request.id}`,
      kind: "decision",
      scope: {
        userId: request.userId,
        project: request.metadata?.project,
        organization: request.metadata?.organization,
      },
      title: decision.objective,
      content: [
        ...decision.reasoning,
        ...decision.nextActions.map((action) => `Next action: ${action}`),
      ].join("\n"),
      intent: undefined,
      tags: this.tagsFrom(request.prompt, decision.objective),
      sourceRequestId: request.id,
      createdAt: now,
      updatedAt: now,
      importance: this.importanceFrom(request.metadata?.priority, decision.confidence),
      metadata: {
        confidence: decision.confidence,
        evidenceCount: decision.evidence.length,
        assumptions: decision.assumptions,
        missingInformation: decision.missingInformation,
      },
    };

    await this.repository.save(record);
    return record;
  }

  async retrieve(query: MemoryQuery): Promise<ExecutiveMemorySnapshot> {
    const records = await this.repository.list(query);
    const now = query.now ?? new Date();
    const matches = records
      .map((record) => this.score(record, query, now))
      .sort((a, b) => b.score - a.score)
      .slice(0, query.limit ?? 10);

    return { query, matches };
  }

  private score(record: MemoryRecord, query: MemoryQuery, now: Date): MemoryMatch {
    const relevance = this.relevance(record, query.text);
    const ageDays = Math.max(0, (now.getTime() - record.updatedAt.getTime()) / DAY_MS);
    const recency = 1 / (1 + ageDays / 30);
    const importance = this.clamp(record.importance);
    const score = 0.55 * relevance + 0.25 * recency + 0.2 * importance;
    return { record, relevance, recency, importance, score };
  }

  private relevance(record: MemoryRecord, text?: string): number {
    if (!text?.trim()) return 0.5;
    const tokens = this.tokenize(text);
    if (!tokens.length) return 0.5;
    const corpus = new Set(
      this.tokenize(`${record.title} ${record.content} ${record.tags.join(" ")}`),
    );
    const hits = tokens.filter((token) => corpus.has(token)).length;
    return hits / tokens.length;
  }

  private tokenize(value: string): string[] {
    return [...new Set(value.toLowerCase().match(/[a-z0-9]+/g) ?? [])];
  }

  private tagsFrom(...values: string[]): string[] {
    return this.tokenize(values.join(" ")).filter((token) => token.length > 2).slice(0, 12);
  }

  private importanceFrom(
    priority: "low" | "normal" | "high" | "critical" | undefined,
    confidence: number,
  ): number {
    const priorityScore = { low: 0.3, normal: 0.5, high: 0.8, critical: 1 }[
      priority ?? "normal"
    ];
    return this.clamp(priorityScore * 0.6 + confidence * 0.4);
  }

  private clamp(value: number): number {
    return Math.max(0, Math.min(1, value));
  }
}
