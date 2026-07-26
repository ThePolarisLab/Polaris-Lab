import assert from "node:assert/strict";
import test from "node:test";
import { buildRuntimeConfig } from "../src/runtimeConfig.js";

test("buildRuntimeConfig trims trailing API slash", () => {
  const config = buildRuntimeConfig({
    VITE_API_BASE_URL: "https://polaris.example.com/",
  });

  assert.equal(config.apiBaseUrl, "https://polaris.example.com");
});

test("buildRuntimeConfig externalizes workspace identity", () => {
  const config = buildRuntimeConfig({
    VITE_WORKSPACE_USER_NAME: "Builder User",
    VITE_WORKSPACE_ORGANIZATION: "Example Organization",
    VITE_WORKSPACE_NAME: "Operations Workspace",
  });

  assert.deepEqual(config.workspace, {
    userName: "Builder User",
    organizationName: "Example Organization",
    workspaceName: "Operations Workspace",
  });
});
