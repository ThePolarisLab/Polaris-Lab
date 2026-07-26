import {
  CertificationCriterion,
  hermesCertificationManifest,
} from "./certificationManifest";

const allowedStatuses = new Set(["planned", "passed", "failed", "deferred", "excluded"]);
const allowedSeverities = new Set(["critical", "high", "medium", "low"]);

function validateCriterion(criterion: CertificationCriterion): void {
  expect(criterion.id).toMatch(/^HCF-\d{3}$/);
  expect(criterion.domain.trim()).not.toBe("");
  expect(criterion.title.trim()).not.toBe("");
  expect(criterion.owner.trim()).not.toBe("");
  expect(allowedSeverities.has(criterion.severity)).toBe(true);
  expect(allowedStatuses.has(criterion.status)).toBe(true);
  expect(criterion.evidenceRequired.length).toBeGreaterThan(0);
  expect(criterion.evidenceRequired.every((item) => item.trim().length > 0)).toBe(true);

  if (criterion.status === "excluded") {
    expect(criterion.exclusionReason?.trim()).toBeTruthy();
  }
}

describe("Hermes certification manifest", () => {
  it("contains unique criteria with complete governance metadata", () => {
    expect(hermesCertificationManifest.length).toBeGreaterThan(0);

    hermesCertificationManifest.forEach(validateCriterion);

    const ids = hermesCertificationManifest.map((criterion) => criterion.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("covers all required certification domains", () => {
    const requiredDomains = [
      "connector-contract",
      "integration",
      "projection",
      "query",
      "traceability",
      "integrity",
      "resilience",
      "security",
      "athena-compatibility",
      "operations",
    ];

    const domains = new Set(
      hermesCertificationManifest.map((criterion) => criterion.domain),
    );

    requiredDomains.forEach((domain) => expect(domains.has(domain)).toBe(true));
  });

  it("requires recorded evidence for every passed criterion", () => {
    const passed = hermesCertificationManifest.filter(
      (criterion) => criterion.status === "passed",
    );

    expect(passed.length).toBeGreaterThan(0);
    passed.forEach((criterion) => {
      expect(criterion.evidenceRequired.length).toBeGreaterThanOrEqual(2);
      expect(
        criterion.evidenceRequired.every(
          (item) => item.includes("/") || item.includes("test"),
        ),
      ).toBe(true);
    });
  });
});