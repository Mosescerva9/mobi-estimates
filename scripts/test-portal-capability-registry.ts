import {
  CAPABILITY_STAGES,
  getPortalCapabilityRegistry,
  isDeliveryGradeCapability,
  PORTAL_CAPABILITY_REGISTRY,
} from "../src/lib/capability-registry";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const registry = getPortalCapabilityRegistry();
const capabilities = registry.capabilities;

assert(registry.schemaVersion === "portal_capability_registry_v1", "portal registry schema version must be explicit");
assert(
  registry.allCustomerDeliveryCapabilitiesDeliveryGrade === false,
  "portal registry must not report customer-delivery capabilities as delivery-grade while P0 gates fail",
);

for (const [name, entry] of Object.entries(capabilities)) {
  assert((CAPABILITY_STAGES as readonly string[]).includes(entry.stage), `${name} has unknown stage ${entry.stage}`);
  assert(entry.deliveryGrade === isDeliveryGradeCapability(entry.stage), `${name} deliveryGrade must derive from stage`);
  assert(entry.deliveryGrade === false, `${name} must not be delivery-grade before production/accuracy validation`);
  assert(entry.summary.length > 20, `${name} must include truthful capability summary`);
  assert(entry.evidence.length > 0, `${name} must point to source evidence`);
}

for (const required of [
  "customer_deliverable_access",
  "final_construction_estimate_delivery",
  "supported_trade_accuracy",
] as const) {
  assert(required in PORTAL_CAPABILITY_REGISTRY, `missing required portal P0 capability: ${required}`);
  const entry = capabilities[required];
  assert(entry.customerVisible === true, `${required} must be marked customer-visible`);
  assert(entry.stage === "planned", `${required} must remain planned/locked until P0 evidence exists`);
  assert(entry.deliveryGrade === false, `${required} must not be delivery-grade`);
}

const finalDeliverySummary = capabilities.final_construction_estimate_delivery.summary.toLowerCase();
for (const term of ["not enabled", "owner", "approval"]) {
  assert(finalDeliverySummary.includes(term), `final delivery summary must mention ${term}`);
}

const deliverableAccessSummary = capabilities.customer_deliverable_access.summary.toLowerCase();
for (const term of ["complete evidence", "supported scope", "required reviews", "owner approval"]) {
  assert(deliverableAccessSummary.includes(term), `customer deliverable access summary must mention ${term}`);
}

console.log(`PASS portal capability registry: checked ${Object.keys(capabilities).length} capabilities`);
