export class MetricCounter {
  private count = 0;

  increment(value = 1): void {
    if (!Number.isFinite(value) || value < 0) {
      throw new RangeError("Counter increments must be finite and non-negative");
    }
    this.count += value;
  }

  value(): number {
    return this.count;
  }

  reset(): void {
    this.count = 0;
  }
}
