export const OBSERVED_PRECISION_RATE_BAND = "0.0005";

const DIFFERENCE_STATUSES = new Set(["price_difference", "fallback_difference"]);
const MATCH_STATUSES = new Set(["match", "fallback_match"]);

function decimalParts(value) {
  const text = String(value ?? "").trim();
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(text);
  if (!match) throw new Error(`Invalid decimal string: ${text || "<empty>"}`);
  const sign = match[1] === "-" ? -1n : 1n;
  const fraction = match[3] || "";
  const magnitude = BigInt(`${match[2]}${fraction}`);
  return { units: sign * magnitude, scale: fraction.length };
}

function pow10(exp) {
  return 10n ** BigInt(exp);
}

function alignedUnits(parts, scale) {
  return parts.units * pow10(scale - parts.scale);
}

function formatUnits(units, scale) {
  const negative = units < 0n;
  const absolute = negative ? -units : units;
  let digits = absolute.toString();
  if (scale === 0) return `${negative && absolute !== 0n ? "-" : ""}${digits}`;
  digits = digits.padStart(scale + 1, "0");
  const integer = digits.slice(0, -scale);
  const fraction = digits.slice(-scale);
  return `${negative && absolute !== 0n ? "-" : ""}${integer}.${fraction}`;
}

export function sumDecimalStrings(values) {
  const parts = values.map(decimalParts);
  if (!parts.length) return "0";
  const scale = Math.max(...parts.map((item) => item.scale));
  const total = parts.reduce((sum, item) => sum + alignedUnits(item, scale), 0n);
  return formatUnits(total, scale);
}

export function compareAbsoluteDecimals(left, right) {
  const a = decimalParts(left);
  const b = decimalParts(right);
  const scale = Math.max(a.scale, b.scale);
  const leftAbs = alignedUnits({ ...a, units: a.units < 0n ? -a.units : a.units }, scale);
  const rightAbs = alignedUnits({ ...b, units: b.units < 0n ? -b.units : b.units }, scale);
  return leftAbs < rightAbs ? -1 : leftAbs > rightAbs ? 1 : 0;
}

export function isObservedPrecisionCandidate(line) {
  if (!DIFFERENCE_STATUSES.has(line?.status)) return false;
  if (compareAbsoluteDecimals(line.rate_difference, "0") === 0) return false;
  return compareAbsoluteDecimals(line.rate_difference, OBSERVED_PRECISION_RATE_BAND) <= 0;
}

function byAbsoluteImpactDescending(left, right) {
  return compareAbsoluteDecimals(right.analytical_impact, left.analytical_impact);
}

export function buildFuelReview(preview) {
  const lines = Array.isArray(preview?.lines) ? preview.lines : [];
  const priceDifferences = lines
    .filter((line) => DIFFERENCE_STATUSES.has(line.status))
    .map((line) => ({
      ...line,
      review_priority: isObservedPrecisionCandidate(line) ? "precision_candidate" : "investigate",
      review_disposition: line.review?.disposition || "not_reviewed",
      is_approved_no_action: line.review?.disposition === "approved_no_action",
    }))
    .sort(byAbsoluteImpactDescending);

  const openPriceDifferences = priceDifferences.filter((line) => !line.is_approved_no_action);
  const approvedDifferences = priceDifferences.filter((line) => line.is_approved_no_action);
  const defPending = lines.filter(
    (line) => line.category === "DEF" && line.quantity_verification_status === "pending_receipt_and_motive",
  );
  const unresolved = lines.filter((line) => line.status === "unresolved");
  const matches = lines.filter((line) => MATCH_STATUSES.has(line.status));

  return {
    priceDifferences,
    openPriceDifferences,
    approvedDifferences,
    investigate: openPriceDifferences.filter((line) => line.review_priority === "investigate"),
    precisionCandidates: openPriceDifferences.filter((line) => line.review_priority === "precision_candidate"),
    defPending,
    unresolved,
    matches,
    netAnalyticalImpact: sumDecimalStrings(priceDifferences.map((line) => line.analytical_impact)),
    openAnalyticalImpact: sumDecimalStrings(openPriceDifferences.map((line) => line.analytical_impact)),
    approvedAnalyticalImpact: sumDecimalStrings(approvedDifferences.map((line) => line.analytical_impact)),
  };
}
