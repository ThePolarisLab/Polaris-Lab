export class MetricGauge {
  private current = 0;

  set(value: number): void {
    if (!Number.isFinite(value)) {
      throw new RangeError("Gauge values must be finite");
    }
    this.current = value;
  }

  increment(value = 1): void {
    this.set(this.current + value);
  }

  decrement(value = 1): void {
    this.set(Math.max(0, this.current - value));
  }

  value(): number {
    return this.current;
  }
}
