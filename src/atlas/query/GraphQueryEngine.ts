import { KnowledgeGraph } from "../graph";
import { GraphPath, GraphPathStep, GraphQueryOptions, TraversalResult } from "./QueryTypes";

const normalizeId = (id: string): string => id.trim();
const normalizeDepth = (maxDepth?: number): number => {
  const depth = maxDepth ?? 3;
  if (!Number.isInteger(depth) || depth < 0 || depth > 20) {
    throw new Error("maxDepth must be an integer between 0 and 20");
  }
  return depth;
};

export class GraphQueryEngine {
  constructor(private readonly graph: KnowledgeGraph) {}

  async traverse(startEntityId: string, options: GraphQueryOptions = {}): Promise<TraversalResult> {
    const startId = normalizeId(startEntityId);
    const start = await this.graph.getEntity(startId);
    if (!start) {
      throw new Error(`Entity not found: ${startId}`);
    }

    const maxDepth = normalizeDepth(options.maxDepth);
    const visited = new Set<string>([start.id]);
    const queue: Array<{ entityId: string; depth: number; path: GraphPathStep[] }> = [
      { entityId: start.id, depth: 0, path: [] },
    ];
    const nodes: TraversalResult["nodes"] = [];

    while (queue.length > 0) {
      const current = queue.shift()!;
      if (current.depth >= maxDepth) {
        continue;
      }

      const neighbors = await this.graph.neighbors(current.entityId, {
        direction: options.direction,
        relationshipTypes: options.relationshipTypes,
      });

      for (const neighbor of neighbors) {
        if (visited.has(neighbor.entity.id)) {
          continue;
        }

        const from = await this.graph.getEntity(current.entityId);
        if (!from) {
          continue;
        }

        const step: GraphPathStep = {
          from,
          relationship: neighbor.relationship,
          to: neighbor.entity,
          direction: neighbor.direction,
        };
        const path = [...current.path, step];
        const depth = current.depth + 1;

        visited.add(neighbor.entity.id);
        nodes.push({ entity: neighbor.entity, depth, path });
        queue.push({ entityId: neighbor.entity.id, depth, path });
      }
    }

    return {
      start,
      nodes,
      visitedEntityIds: [...visited],
      maxDepth,
    };
  }

  async shortestPath(
    startEntityId: string,
    endEntityId: string,
    options: GraphQueryOptions = {},
  ): Promise<GraphPath | undefined> {
    const startId = normalizeId(startEntityId);
    const endId = normalizeId(endEntityId);
    const [start, end] = await Promise.all([
      this.graph.getEntity(startId),
      this.graph.getEntity(endId),
    ]);

    if (!start) {
      throw new Error(`Entity not found: ${startId}`);
    }
    if (!end) {
      throw new Error(`Entity not found: ${endId}`);
    }
    if (start.id === end.id) {
      return { start, end, steps: [], depth: 0 };
    }

    const maxDepth = normalizeDepth(options.maxDepth);
    const visited = new Set<string>([start.id]);
    const queue: Array<{ entityId: string; path: GraphPathStep[] }> = [
      { entityId: start.id, path: [] },
    ];

    while (queue.length > 0) {
      const current = queue.shift()!;
      if (current.path.length >= maxDepth) {
        continue;
      }

      const currentEntity = await this.graph.getEntity(current.entityId);
      if (!currentEntity) {
        continue;
      }

      const neighbors = await this.graph.neighbors(current.entityId, {
        direction: options.direction,
        relationshipTypes: options.relationshipTypes,
      });

      for (const neighbor of neighbors) {
        if (visited.has(neighbor.entity.id)) {
          continue;
        }

        const step: GraphPathStep = {
          from: currentEntity,
          relationship: neighbor.relationship,
          to: neighbor.entity,
          direction: neighbor.direction,
        };
        const path = [...current.path, step];

        if (neighbor.entity.id === end.id) {
          return { start, end, steps: path, depth: path.length };
        }

        visited.add(neighbor.entity.id);
        queue.push({ entityId: neighbor.entity.id, path });
      }
    }

    return undefined;
  }
}
