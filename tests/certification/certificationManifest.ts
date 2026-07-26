export type CertificationStatus =
  | "planned"
  | "passed"
  | "failed"
  | "deferred"
  | "excluded";

export type CertificationSeverity = "critical" | "high" | "medium" | "low";

export interface CertificationCriterion {
  id: string;
  domain: string;
  title: string;
  owner: string;
  severity: CertificationSeverity;
  evidenceRequired: string[];
  status: CertificationStatus;
  exclusionReason?: string;
}

export const hermesCertificationManifest: CertificationCriterion[] = [
  {
    id: "HCF-001",
    domain: "connector-contract",
    title: "Connector implementations conform to provider-neutral contracts",
    owner: "Hermes",
    severity: "critical",
    evidenceRequired: ["automated contract tests", "connector capability declaration"],
    status: "planned",
  },
  {
    id: "HCF-002",
    domain: "integration",
    title: "Source observations produce governed evidence envelopes",
    owner: "Hermes",
    severity: "critical",
    evidenceRequired: ["end-to-end test", "provenance assertion"],
    status: "planned",
  },
  {
    id: "HCF-003",
    domain: "projection",
    title: "Governed evidence projects deterministically into executive entities",
    owner: "Hermes",
    severity: "critical",
    evidenceRequired: ["projection test", "version assertion"],
    status: "planned",
  },
  {
    id: "HCF-004",
    domain: "query",
    title: "Executive queries preserve organization isolation and stable ordering",
    owner: "Hermes",
    severity: "critical",
    evidenceRequired: ["query test", "cross-organization negative test"],
    status: "planned",
  },
  {
    id: "HCF-005",
    domain: "traceability",
    title: "Executive results trace back to source observations",
    owner: "Hermes",
    severity: "critical",
    evidenceRequired: ["evidence reference", "source provenance chain"],
    status: "planned",
  },
  {
    id: "HCF-006",
    domain: "integrity",
    title: "Replay and duplicate ingestion remain deterministic and idempotent",
    owner: "Hermes",
    severity: "high",
    evidenceRequired: ["replay test", "duplicate-ingestion test"],
    status: "planned",
  },
  {
    id: "HCF-007",
    domain: "resilience",
    title: "Partial failure and restart recover from durable checkpoints",
    owner: "Hermes",
    severity: "high",
    evidenceRequired: ["failure-injection test", "checkpoint recovery assertion"],
    status: "planned",
  },
  {
    id: "HCF-008",
    domain: "security",
    title: "Secrets remain outside evidence, logs, and domain state",
    owner: "Security",
    severity: "critical",
    evidenceRequired: ["secret-boundary review", "negative serialization test"],
    status: "planned",
  },
  {
    id: "HCF-009",
    domain: "athena-compatibility",
    title: "Athena consumes Hermes outputs only through governed contracts",
    owner: "Athena",
    severity: "critical",
    evidenceRequired: ["boundary test", "reasoning evidence reference"],
    status: "planned",
  },
  {
    id: "HCF-010",
    domain: "operations",
    title: "Health and failure signals are observable without exposing secrets",
    owner: "Mission Control",
    severity: "high",
    evidenceRequired: ["health contract test", "operational evidence sample"],
    status: "planned",
  },
];
