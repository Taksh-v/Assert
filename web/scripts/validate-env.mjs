const requiredInProduction = ["ASSEST_API_URL"];
const isProductionBuild =
  process.env.NODE_ENV === "production" || process.env.npm_lifecycle_event === "build";

const missing = requiredInProduction.filter((key) => !process.env[key]);

if (isProductionBuild && missing.length > 0) {
  console.error(`Missing required production env: ${missing.join(", ")}`);
  process.exit(1);
}

const publicBackendUrl = process.env.NEXT_PUBLIC_API_URL;
if (isProductionBuild && publicBackendUrl) {
  console.warn(
    "NEXT_PUBLIC_API_URL is set in production. Prefer ASSEST_API_URL with the /api/backend proxy to avoid browser-side backend coupling.",
  );
}

console.log("Frontend environment validated.");
