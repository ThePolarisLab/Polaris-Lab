import {
  ExecutiveAlert,
  ExecutiveCustomer,
  ExecutiveDriver,
  ExecutiveFinancialSnapshot,
  ExecutiveKpi,
  ExecutiveLoad,
  ExecutiveTask,
  ExecutiveVehicle,
} from "./contracts";
import { ExecutiveRepository } from "./repository";

export interface ExecutiveDashboard {
  readonly customers: readonly ExecutiveCustomer[];
  readonly loads: readonly ExecutiveLoad[];
  readonly vehicles: readonly ExecutiveVehicle[];
  readonly drivers: readonly ExecutiveDriver[];
  readonly financialSnapshots: readonly ExecutiveFinancialSnapshot[];
  readonly tasks: readonly ExecutiveTask[];
  readonly alerts: readonly ExecutiveAlert[];
  readonly kpis: readonly ExecutiveKpi[];
}

export class ExecutiveQueryService {
  constructor(private readonly repository: ExecutiveRepository) {}

  async getExecutiveDashboard(): Promise<ExecutiveDashboard> {
    const [customers, loads, vehicles, drivers, financialSnapshots, tasks, alerts, kpis] = await Promise.all([
      this.repository.listByKind<ExecutiveCustomer>("customer"),
      this.repository.listByKind<ExecutiveLoad>("load"),
      this.repository.listByKind<ExecutiveVehicle>("vehicle"),
      this.repository.listByKind<ExecutiveDriver>("driver"),
      this.repository.listByKind<ExecutiveFinancialSnapshot>("financial-snapshot"),
      this.repository.listByKind<ExecutiveTask>("task"),
      this.repository.listByKind<ExecutiveAlert>("alert"),
      this.repository.listByKind<ExecutiveKpi>("kpi"),
    ]);

    return Object.freeze({ customers, loads, vehicles, drivers, financialSnapshots, tasks, alerts, kpis });
  }

  async getPriorityAlerts(): Promise<readonly ExecutiveAlert[]> {
    const rank = { critical: 0, warning: 1, info: 2 } as const;
    const alerts = await this.repository.listByKind<ExecutiveAlert>("alert");
    return Object.freeze([...alerts].sort((a, b) => rank[a.severity] - rank[b.severity]));
  }
}

export interface ExecutiveBriefing {
  readonly generatedAt: string;
  readonly headline: string;
  readonly criticalAlerts: readonly ExecutiveAlert[];
  readonly openTasks: readonly ExecutiveTask[];
  readonly activeLoads: number;
  readonly availableVehicles: number;
  readonly availableDrivers: number;
  readonly latestFinancialSnapshot?: ExecutiveFinancialSnapshot;
}

export class ExecutiveBriefingService {
  constructor(
    private readonly queryService: ExecutiveQueryService,
    private readonly clock: () => Date = () => new Date(),
  ) {}

  async generate(): Promise<ExecutiveBriefing> {
    const dashboard = await this.queryService.getExecutiveDashboard();
    const criticalAlerts = dashboard.alerts.filter((alert) => alert.severity === "critical");
    const openTasks = dashboard.tasks.filter((task) => task.status === "open" || task.status === "in-progress");
    const activeLoads = dashboard.loads.filter((load) => load.status === "dispatched" || load.status === "in-transit").length;
    const availableVehicles = dashboard.vehicles.filter((vehicle) => vehicle.status === "available").length;
    const availableDrivers = dashboard.drivers.filter((driver) => driver.status === "available").length;
    const latestFinancialSnapshot = [...dashboard.financialSnapshots].sort((a, b) => b.asOf.localeCompare(a.asOf))[0];

    const headline = criticalAlerts.length > 0
      ? `${criticalAlerts.length} critical executive alert${criticalAlerts.length === 1 ? "" : "s"} require attention.`
      : "No critical executive alerts require attention.";

    return Object.freeze({
      generatedAt: this.clock().toISOString(),
      headline,
      criticalAlerts: Object.freeze(criticalAlerts),
      openTasks: Object.freeze(openTasks),
      activeLoads,
      availableVehicles,
      availableDrivers,
      latestFinancialSnapshot,
    });
  }
}
