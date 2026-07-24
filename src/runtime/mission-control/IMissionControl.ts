import { MissionControlSnapshot } from "./MissionControlSnapshot";

export interface IMissionControl {
  snapshot(): MissionControlSnapshot;
}
