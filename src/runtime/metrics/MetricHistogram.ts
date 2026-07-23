export interface HistogramSnapshot {
  readonly count: number;
  readonly min: number;
  readonly max: number;
  readonly average: number;
  readonly p50: number;
  readonly p95: number;
  readonly p99: number;
}

const EMPTY: HistogramSnapshot = Object.freeze({
  count: 0,
  min: 0,
  max: 0,
  average: 0,
  p50: 0,
  p95: 0,
  p99: 0,
});

export class MetricHistogram {
  private readonly samples: number[] = [];

  record(value: number): void {
    if (!Number.isFinite(value) || value < 0) {
      throw new RangeError("Histogram values must be finite and non-negative");
    }
    this.samples.push(value);
  }

  snapshot(): HistogramSnapshot {
    if (this.samples.length === 0) {
      return EMPTY;
    }

    const sorted = [...this.samples].sort((left, right) => left - right);
    const total = sorted.reduce((sum, sample) => sum + sample, 0);
    return Object.freeze({
      count: sorted.length,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      average: total / sorted.length,
      p50: this.percentile(sorted, 0.5),
      p95: this.percentile(sorted, 0.95),
      p99: this.percentile(sorted, 0.99),
    });
  }

  private percentile(sorted: readonly number[], percentile: number): number {
    const index = Math.max(0, Math.ceil(percentile * sorted.length) - 1);
    return sorted[index];
  }
}
