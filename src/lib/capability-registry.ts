export const CAPABILITY_REGISTRY_SCHEMA_VERSION = "portal_capability_registry_v1" as const;

/**
 * Stage names are the audit checklist's exact taxonomy. Shorter labels such as
 * "source"/"staging"/"production" are deliberately not accepted: they blur the
 * difference between "code exists" and "verified in that environment", which is
 * the confusion audit P0-1 exists to prevent.
 */
export const CAPABILITY_STAGES = [
  "planned",
  "source_implemented",
  "staging_verified",
  "production_verified",
  "accuracy_validated",
] as const;
export type CapabilityStage = (typeof CAPABILITY_STAGES)[number];

export type CapabilityRegistryEntry = {
  stage: CapabilityStage;
  deliveryGrade: boolean;
  customerVisible: boolean;
  summary: string;
  evidence: string[];
};

const DELIVERY_GRADE_STAGES = new Set<CapabilityStage>(["production_verified", "accuracy_validated"]);

export function isCapabilityStage(stage: unknown): stage is CapabilityStage {
  return typeof stage === "string" && (CAPABILITY_STAGES as readonly string[]).includes(stage);
}

export function isDeliveryGradeCapability(stage: CapabilityStage | string | null | undefined): stage is CapabilityStage {
  return isCapabilityStage(stage) && DELIVERY_GRADE_STAGES.has(stage);
}

/**
 * Truthful portal capability registry for audit P0-1.
 *
 * This is a source-of-truth manifest for the portal/customer-facing surfaces, not
 * a marketing claim. It intentionally distinguishes source_implemented/staging_verified
 * admin workflow evidence from production_verified/accuracy_validated delivery support
 * so UI, docs, or tests cannot be mistaken for final construction-estimate readiness.
 */
export const PORTAL_CAPABILITY_REGISTRY = {
  customer_intake: {
    stage: "source_implemented",
    deliveryGrade: false,
    customerVisible: true,
    summary: "Customer project intake exists in source; live production behavior is not audit-verified.",
    evidence: ["src/app/portal/projects/new", "supabase/migrations"],
  },
  document_register_review: {
    stage: "source_implemented",
    deliveryGrade: false,
    customerVisible: false,
    summary: "Admin document register/review workflow exists in source; canonical revision/addendum completeness is not proven.",
    evidence: ["src/lib/estimate-jobs.ts", "src/app/admin/projects/[id]"],
  },
  admin_estimate_workflow: {
    stage: "source_implemented",
    deliveryGrade: false,
    customerVisible: false,
    summary: "Internal workflow labels and review panels exist; they are not final customer-delivery authorization.",
    evidence: ["src/app/admin/projects/[id]/AutomationV1Panel.tsx", "src/lib/estimate-jobs.ts"],
  },
  customer_deliverable_access: {
    stage: "planned",
    deliveryGrade: false,
    customerVisible: true,
    summary: "Customer deliverable access is deliberately locked until complete evidence, supported scope, required reviews, and owner approval are persisted.",
    evidence: ["src/lib/estimate-jobs.ts", "supabase/migrations/0021_restrict_deliverables_write_to_admin.sql"],
  },
  final_construction_estimate_delivery: {
    stage: "planned",
    deliveryGrade: false,
    customerVisible: true,
    summary: "Autonomous final construction-estimate delivery is not enabled and remains owner-approval gated.",
    evidence: ["src/lib/estimate-jobs.ts", "supabase/migrations/0022_lock_final_delivery_project_status.sql"],
  },
  supported_trade_accuracy: {
    stage: "planned",
    deliveryGrade: false,
    customerVisible: true,
    summary: "No portal-supported trade lane is production_verified or accuracy_validated for autonomous customer delivery.",
    evidence: ["Audits/GPT-5.6-Sol-Architecture-Audit-2026-07-10/15-Production-Readiness-Checklist.md"],
  },
} as const satisfies Record<string, CapabilityRegistryEntry>;

export type PortalCapabilityName = keyof typeof PORTAL_CAPABILITY_REGISTRY;

export function getPortalCapabilityRegistry() {
  const capabilities = Object.fromEntries(
    Object.entries(PORTAL_CAPABILITY_REGISTRY).map(([name, entry]) => [
      name,
      {
        ...entry,
        deliveryGrade: DELIVERY_GRADE_STAGES.has(entry.stage),
      },
    ]),
  ) as unknown as Record<PortalCapabilityName, CapabilityRegistryEntry>;

  return {
    schemaVersion: CAPABILITY_REGISTRY_SCHEMA_VERSION,
    capabilities,
    allCustomerDeliveryCapabilitiesDeliveryGrade: Object.values(capabilities)
      .filter((entry) => entry.customerVisible)
      .every((entry) => entry.deliveryGrade),
  };
}
