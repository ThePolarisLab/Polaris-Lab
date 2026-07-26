export type CertificationStatus = "planned" | "passed" | "failed" | "deferred" | "excluded";
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

const traceabilityEvidence = [
  "tests/certification/endToEndTraceability.test.ts",
  "docs/hermes/HERMES_END_TO_END_TRACEABILITY.md",
];

const resilienceSecurityEvidence = [
  "tests/certification/resilienceSecurityCertification.test.ts",
  "docs/hermes/HERMES_RESILIENCE_SECURITY_CERTIFICATION.md",
  "src/hermes/resilience.ts",
];

export const hermesCertificationManifest: CertificationCriterion[] = [
  { id: "HCF-001", domain: "connector-contract", title: "Connector implementations conform to provider-neutral contracts", owner: "Hermes", severity: "critical", evidenceRequired: ["tests/certification/referenceConnectorCertification.test.ts", "docs/hermes/HERMES_REFERENCE_CONNECTOR_CERTIFICATION.md"], status: "passed" },
  { id: "HCF-002", domain: "integration", title: "Source observations produce governed evidence envelopes", owner: "Hermes", severity: "critical", evidenceRequired: traceabilityEvidence, status: "passed" },
  { id: "HCF-003", domain: "projection", title: "Governed evidence projects deterministically into executive entities", owner: "Hermes", severity: "critical", evidenceRequired: ["tests/certification/endToEndTraceability.test.ts", "tests/hermes/ExecutiveProjectionEngine.test.ts"], status: "passed" },
  { id: "HCF-004", domain: "query", title: "Executive queries preserve organization isolation and stable ordering", owner: "Hermes", severity: "critical", evidenceRequired: ["tests/certification/endToEndTraceability.test.ts", "tests/hermes/ExecutiveQueryEngine.test.ts"], status: "passed" },
  { id: "HCF-005", domain: "traceability", title: "Executive results trace back to source observations", owner: "Hermes", severity: "critical", evidenceRequired: traceabilityEvidence, status: "passed" },
  { id: "HCF-006", domain: "integrity", title: "Replay and duplicate ingestion remain deterministic and idempotent", owner: "Hermes", severity: "high", evidenceRequired: ["tests/certification/endToEndTraceability.test.ts", "tests/hermes/ExecutiveProjectionEngine.test.ts"], status: "passed" },
  { id: "HCF-007", domain: "resilience", title: "Partial failure and restart recover from durable checkpoints", owner: "Hermes", severity: "high", evidenceRequired: resilienceSecurityEvidence, status: "passed" },
  { id: "HCF-008", domain: "security", title: "Secrets remain outside evidence, logs, and domain state", owner: "Security", severity: "critical", evidenceRequired: resilienceSecurityEvidence, status: "passed" },
  { id: "HCF-009", domain: "athena-compatibility", title: "Athena consumes Hermes outputs only through governed contracts", owner: "Athena", severity: "critical", evidenceRequired: ["boundary test", "reasoning evidence reference"], status: "planned" },
  { id: "HCF-010", domain: "operations", title: "Health and failure signals are observable without exposing secrets", owner: "Mission Control", severity: "high", evidenceRequired: resilienceSecurityEvidence, status: "passed" },
];
