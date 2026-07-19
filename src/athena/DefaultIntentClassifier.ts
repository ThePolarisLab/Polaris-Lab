import { IntentClassifier } from "./ports";
import { AthenaIntent, AthenaRequest } from "./types";

const RULES: ReadonlyArray<{
  intent: AthenaIntent;
  keywords: readonly string[];
}> = [
  { intent: "finance", keywords: ["cash flow", "revenue", "expense", "profit", "invoice", "financial"] },
  { intent: "calendar", keywords: ["calendar", "schedule", "appointment"] },
  { intent: "meeting", keywords: ["meeting", "agenda", "minutes"] },
  { intent: "email", keywords: ["email", "inbox", "reply", "draft"] },
  { intent: "strategy", keywords: ["strategy", "strategic", "competitive advantage"] },
  { intent: "planning", keywords: ["plan", "roadmap", "milestone"] },
  { intent: "decision", keywords: ["decide", "recommend", "should we", "best option"] },
  { intent: "analysis", keywords: ["analyze", "analysis", "compare", "trend", "risk"] },
  { intent: "research", keywords: ["research", "investigate", "study"] },
  { intent: "project", keywords: ["project", "sprint", "backlog", "release"] },
  { intent: "task", keywords: ["task", "todo", "remind", "action item"] },
  { intent: "document", keywords: ["document", "report", "file", "pdf"] },
  { intent: "business", keywords: ["business", "company", "customer", "operation"] },
  { intent: "search", keywords: ["find", "search", "look up"] },
  { intent: "knowledge", keywords: ["explain", "what is", "how does"] },
];

export class DefaultIntentClassifier implements IntentClassifier {
  async classify(request: AthenaRequest): Promise<AthenaIntent> {
    const prompt = request.prompt.trim().toLowerCase();

    if (!prompt) {
      return "unknown";
    }

    for (const rule of RULES) {
      if (rule.keywords.some((keyword) => prompt.includes(keyword))) {
        return rule.intent;
      }
    }

    return "general";
  }
}
