import { GraphPath } from "../query";
import { ExplainPathOptions, ExplanationEvidence, ExplanationStep, GraphExplanation } from "./ExplanationTypes";

const labelEntity = (name: string, type: string, includeType: boolean): string =>
  includeType ? `${name} (${type})` : name;

const relationshipPhrase = (type: string): string => type.replaceAll("_", " ");

export class ExplainabilityEngine {
  explainPath(path: GraphPath, options: ExplainPathOptions = {}): GraphExplanation {
    if (!path.start || !path.end) {
      throw new Error("A valid graph path is required");
    }

    if (path.steps.length !== path.depth) {
      throw new Error("Graph path depth does not match its steps");
    }

    const includeTypes = options.includeEntityTypes ?? true;
    const includeIds = options.includeEvidenceIds ?? true;

    const steps: ExplanationStep[] = path.steps.map((step, index) => {
      const from = labelEntity(step.from.name, step.from.type, includeTypes);
      const to = labelEntity(step.to.name, step.to.type, includeTypes);
      return {
        position: index + 1,
        statement: `${from} ${relationshipPhrase(step.relationship.type)} ${to}.`,
        from: step.from,
        to: step.to,
        relationship: step.relationship,
        confidence: step.relationship.confidence,
      };
    });

    const evidence: ExplanationEvidence[] = [
      {
        entityId: path.start.id,
        entityName: path.start.name,
        confidence: 1,
      },
      ...steps.map((step) => ({
        entityId: step.to.id,
        entityName: step.to.name,
        relationshipId: includeIds ? step.relationship.id : undefined,
        relationshipType: step.relationship.type,
        confidence: step.confidence,
      })),
    ];

    const confidence = steps.length === 0
      ? 1
      : Math.min(...steps.map((step) => step.confidence));

    const summary = path.steps.length === 0
      ? `${path.start.name} is the requested entity.`
      : `${path.start.name} is connected to ${path.end.name} through ${path.depth} relationship${path.depth === 1 ? "" : "s"}.`;

    return {
      summary,
      narrative: steps.map((step) => step.statement).join(" "),
      start: path.start,
      end: path.end,
      path,
      steps,
      evidence,
      confidence,
    };
  }
}
