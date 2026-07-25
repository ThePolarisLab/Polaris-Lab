import {
  ExecutiveAlert,
  ExecutiveCustomer,
  ExecutiveDriver,
  ExecutiveFinancialSnapshot,
  ExecutiveLoad,
  ExecutiveTask,
  ExecutiveVehicle,
  Money,
} from "../executive/contracts";
import { ExecutiveQueryRepository, PageResult, QueryContext } from "./contracts";

export interface ExecutiveDashboard {
  readonly generatedAt: string;
  readonly customers: { readonly active: number; readonly atRisk: number };
  readonly fleet: { readonly available: number; readonly maintenance: number; readonly averageUtilizationPercent?: number };
  readonly operations: { readonly activeLoads: number; readonly availableDrivers: number };
  readonly finance?: { readonly asOf: string; readonly cashPosition?: Money; readonly accountsReceivable?: Money; readonly revenue?: Money; readonly netProfit?: Money };
  readonly risk: { readonly criticalAlerts: number; readonly openCriticalTasks: number };
}

export class ExecutiveQueryEngine {
  constructor(
    private readonly repository: ExecutiveQueryRepository,
    private readonly clock: () => string = () => new Date().toISOString(),
  ) {}

  customers(context: QueryContext, options: { atRiskOnly?: boolean; limit?: number } = {}): Promise<PageResult<ExecutiveCustomer>> {
    return this.repository.search(context, {
      kind: "customer",
      filters: options.atRiskOnly ? [{ field: "status", operator: "eq", value: "at-risk" }] : undefined,
      sort: [{ field: "riskScore", direction: "desc" }],
      page: { limit: options.limit ?? 50 },
    });
  }

  fleet(context: QueryContext, options: { status?: ExecutiveVehicle["status"]; utilizationBelow?: number; limit?: number } = {}): Promise<PageResult<ExecutiveVehicle>> {
    const filters = [];
    if (options.status) filters.push({ field: "status", operator: "eq" as const, value: options.status });
    if (options.utilizationBelow !== undefined) filters.push({ field: "utilizationPercent", operator: "lt" as const, value: options.utilizationBelow });
    return this.repository.search(context, { kind: "vehicle", filters, sort: [{ field: "utilizationPercent", direction: "asc" }], page: { limit: options.limit ?? 50 } });
  }

  financial(context: QueryContext): Promise<PageResult<ExecutiveFinancialSnapshot>> {
    return this.repository.search(context, { kind: "financial-snapshot", sort: [{ field: "asOf", direction: "desc" }], page: { limit: 1 } });
  }

  operations(context: QueryContext, options: { status?: ExecutiveLoad["status"]; limit?: number } = {}): Promise<PageResult<ExecutiveLoad>> {
    return this.repository.search(context, { kind: "load", filters: options.status ? [{ field: "status", operator: "eq", value: options.status }] : undefined, sort: [{ field: "updatedAt", direction: "desc" }], page: { limit: options.limit ?? 50 } });
  }

  tasks(context: QueryContext, options: { openOnly?: boolean; criticalOnly?: boolean; limit?: number } = {}): Promise<PageResult<ExecutiveTask>> {
    const filters = [];
    if (options.openOnly) filters.push({ field: "status", operator: "in" as const, value: ["open", "in-progress"] });
    if (options.criticalOnly) filters.push({ field: "priority", operator: "eq" as const, value: "critical" });
    return this.repository.search(context, { kind: "task", filters, sort: [{ field: "dueAt", direction: "asc" }], page: { limit: options.limit ?? 50 } });
  }

  alerts(context: QueryContext, options: { criticalOnly?: boolean; unacknowledgedOnly?: boolean; limit?: number } = {}): Promise<PageResult<ExecutiveAlert>> {
    const filters = options.criticalOnly ? [{ field: "severity", operator: "eq" as const, value: "critical" }] : [];
    return this.repository.search(context, { kind: "alert", filters, predicate: options.unacknowledgedOnly ? (alert) => !alert.acknowledgedAt : undefined, sort: [{ field: "updatedAt", direction: "desc" }], page: { limit: options.limit ?? 50 } });
  }

  async dashboard(context: QueryContext): Promise<ExecutiveDashboard> {
    const [activeCustomers, atRiskCustomers, availableVehicles, maintenanceVehicles, vehicles, activeLoads, availableDrivers, financial, criticalAlerts, criticalTasks] = await Promise.all([
      this.repository.count<ExecutiveCustomer>(context, { kind: "customer", filters: [{ field: "status", operator: "eq", value: "active" }] }),
      this.repository.count<ExecutiveCustomer>(context, { kind: "customer", filters: [{ field: "status", operator: "eq", value: "at-risk" }] }),
      this.repository.count<ExecutiveVehicle>(context, { kind: "vehicle", filters: [{ field: "status", operator: "eq", value: "available" }] }),
      this.repository.count<ExecutiveVehicle>(context, { kind: "vehicle", filters: [{ field: "status", operator: "eq", value: "maintenance" }] }),
      this.repository.search<ExecutiveVehicle>(context, { kind: "vehicle", page: { limit: 500 } }),
      this.repository.count<ExecutiveLoad>(context, { kind: "load", filters: [{ field: "status", operator: "in", value: ["planned", "dispatched", "in-transit"] }] }),
      this.repository.count<ExecutiveDriver>(context, { kind: "driver", filters: [{ field: "status", operator: "eq", value: "available" }] }),
      this.financial(context),
      this.repository.count<ExecutiveAlert>(context, { kind: "alert", filters: [{ field: "severity", operator: "eq", value: "critical" }], predicate: (alert) => !alert.acknowledgedAt }),
      this.repository.count<ExecutiveTask>(context, { kind: "task", filters: [{ field: "priority", operator: "eq", value: "critical" }, { field: "status", operator: "in", value: ["open", "in-progress"] }] }),
    ]);
    const utilization = vehicles.items.map((vehicle) => vehicle.utilizationPercent).filter((value): value is number => value !== undefined);
    const snapshot = financial.items[0];
    return Object.freeze({
      generatedAt: this.clock(),
      customers: { active: activeCustomers, atRisk: atRiskCustomers },
      fleet: { available: availableVehicles, maintenance: maintenanceVehicles, averageUtilizationPercent: utilization.length ? utilization.reduce((sum, value) => sum + value, 0) / utilization.length : undefined },
      operations: { activeLoads, availableDrivers },
      finance: snapshot ? { asOf: snapshot.asOf, cashPosition: snapshot.cashPosition, accountsReceivable: snapshot.accountsReceivable, revenue: snapshot.revenue, netProfit: snapshot.netProfit } : undefined,
      risk: { criticalAlerts, openCriticalTasks: criticalTasks },
    });
  }
}
