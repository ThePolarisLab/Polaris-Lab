export function buildRuntimeConfig(env = {}) {
  const apiBaseUrl = (env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const userName = env.VITE_WORKSPACE_USER_NAME || "Executive";
  const organizationName = env.VITE_WORKSPACE_ORGANIZATION || "Mor Logistics Manitoba Limited";
  const workspaceName = env.VITE_WORKSPACE_NAME || "Executive Workspace";
  const accessToken = env.VITE_POLARIS_ACCESS_TOKEN || "";
  const organizationId = env.VITE_POLARIS_ORGANIZATION_ID || "";

  return Object.freeze({
    apiBaseUrl,
    auth: Object.freeze({
      accessToken,
      organizationId,
    }),
    workspace: Object.freeze({
      userName,
      organizationName,
      workspaceName,
    }),
  });
}

export const runtimeConfig = buildRuntimeConfig(import.meta.env);
