// Shapes returned by the Sentinel AI API (docs/09_BACKEND/API_DESIGN.md).
// Agent outputs are typed only as far as the dashboard reads them.

export type CaseStatus = "RECEIVED" | "INVESTIGATING" | "AWAITING_REVIEW" | "INVESTIGATION_FAILED" | "DECIDED";
export type AnalystAction = "BLOCK" | "ESCALATE" | "MONITOR" | "CLEAR";
export const ANALYST_ACTIONS: AnalystAction[] = ["BLOCK", "ESCALATE", "MONITOR", "CLEAR"];

export interface User {
  username: string;
  display_name: string;
}

export interface CaseSummary {
  risk_score: number | null;
  recommended_action: string | null;
  score_band_action: string | null;
  confidence: string | null;
  sar_recommended: boolean | null;
  report_generator: string | null;
  validation_status: string | null;
  pipeline_status: string | null;
  requires_human_review: boolean;
  priority_rank: number;
}

export interface AlertInfo {
  alert_id: string | null;
  source: "API" | "SYNTHETIC_FEED" | "DATASET_RUN";
  run_id?: string | null;
  source_system: string | null;
  received_at_utc: string;
}

export interface CaseListItem {
  case_id: string;
  status: CaseStatus;
  created_at_utc: string;
  updated_at_utc: string;
  transaction_id: string | null;
  amount: string | null;
  currency: string | null;
  alert: AlertInfo;
  summary: CaseSummary;
  analyst_action: AnalystAction | null;
}

export interface CaseList {
  total: number;
  limit: number;
  offset: number;
  items: CaseListItem[];
  prototype_notice: string;
}

export interface AnalystDecision {
  decision_id: string;
  decided_at_utc: string;
  analyst_id: string;
  analyst_name: string | null;
  action: AnalystAction;
  rationale: string;
  system_recommended_action: string | null;
  system_risk_score: number | null;
  report_validation_status: string | null;
  agrees_with_system: boolean | null;
  supersedes_decision_id: string | null;
}

export interface AuditEvent {
  event_id: string;
  event_type: string;
  at_utc: string;
  actor: string;
  details: Record<string, unknown>;
}

export interface Fact {
  fact_id: string;
  section: string;
  label: string;
  value: string;
  source_agent: string;
  source: string;
  source_field: string;
  source_mode: string | null;
  observed_at: string | null;
  reference_id: string | null;
}

export interface Statement {
  text: string;
  fact_ids: string[];
  origin: "LLM" | "TEMPLATE" | "SYSTEM";
  added_fact_ids: string[];
}

export interface ReportSection {
  section: string;
  title: string;
  statements: Statement[];
}

export interface Report {
  agent5_run_id: string;
  status: string;
  generator: string | null;
  llm_model: string | null;
  fallback_reason: string | null;
  warnings: string[];
  sections: ReportSection[];
  evidence_bundle: { facts: Fact[]; bundle_hash: string; missing_inputs: string[] } | null;
  validation_status: string;
  report_note: string;
}

export interface ValidationCheck {
  check: string;
  description: string;
  passed: boolean;
  items_checked: number;
  issues: { section: string | null; statement_index: number | null; reason: string; text?: string | null }[];
}

export interface Validation {
  status: string;
  checks: ValidationCheck[];
  checks_passed: number;
  checks_total: number;
  validator_version: string;
  analyst_warning: string | null;
}

export interface ScoreComponent {
  signal: string;
  weight: number;
  available: boolean;
  value: number | null;
  contribution: number | null;
  rationale: string;
}

export interface RegulatoryMatch {
  reference_id: string;
  trigger: string;
  organization: string;
  document_name: string;
  section: string;
  pdf_page: number | null;
  excerpt: string;
  verification_status: string;
  mapping_rationale: string;
}

export interface Agent4Output {
  status: string;
  risk_score: number | null;
  score_band_action: string | null;
  recommended_action: string;
  confidence: string;
  confidence_reasons: string[];
  evidence_coverage: number | null;
  unavailable_signals: string[];
  score_breakdown: ScoreComponent[];
  overrides_applied: { rule_id: string; description: string; minimum_action: string }[];
  sar_recommendation: { recommended: boolean; basis: string[]; note: string };
  regulatory_matches: RegulatoryMatch[];
  warnings: string[];
  config_version: string | null;
  mapping_version: string | null;
  config_approval_status?: string | null;
  config_snapshot?: { monitor_threshold: number; escalate_threshold: number; block_threshold: number } | null;
}

export interface ProviderResult {
  source: string;
  source_mode: string;
  status: string;
  requested_entity_id: string | null;
  retrieved_at: string | null;
  warnings: string[];
}

export interface TraceRecord {
  node: string;
  outcome: "OK" | "ERROR";
  output_status: string | null;
  started_at_utc: string;
  duration_ms: number;
  error: string | null;
}

export interface Investigation {
  agent1_output?: { status: string; combined_confidence: number | null; anomaly_score: number | null; isolation_score: number | null };
  agent2_output?: Record<string, unknown> & { status: string; warnings: string[] };
  agent3_output?: { status: string; findings: unknown[]; warnings: string[] };
  agent4_output?: Agent4Output;
  agent5_output?: Report;
  validation_output?: Validation;
  rejected_reports?: { reason: string; validation: Validation }[];
  pipeline_trace?: TraceRecord[];
  pipeline_status?: string;
  halt_reason?: string | null;
}

export interface Transaction {
  raw_record_id: string;
  source_dataset: string;
  amount: string;
  currency: string;
  timestamp: string | null;
  channel: string;
  sender: { account_id: string | null; customer_id: string | null };
  receiver: { account_id: string | null };
  metadata: { transaction_type?: string | null } | null;
}

export interface CaseRecord {
  case_id: string;
  status: CaseStatus;
  created_at_utc: string;
  updated_at_utc: string;
  prototype_notice: string;
  alert: AlertInfo;
  transaction: Transaction;
  summary: CaseSummary;
  investigation: Investigation | null;
  investigation_error: string | null;
  analyst_decision: AnalystDecision | null;
  decisions: AnalystDecision[];
  audit_trail: AuditEvent[];
}

export interface NetworkNode {
  id: string;
  roles: string[];
  finding_ids: string[];
  patterns: string[];
}

export interface NetworkEdge {
  id: string;
  source: string;
  target: string;
  raw_record_id: string | null;
  amount: number | null;
  currency: string | null;
  timestamp_utc: string | null;
  channel: string | null;
  investigated: boolean;
  finding_ids: string[];
  patterns: string[];
}

export interface NetworkFinding {
  finding_id: string;
  pattern_type: string;
  rule_id: string;
  subject_account_id: string;
  related_account_ids: string[];
  heuristic_score: number | null;
  transfer_count: number | null;
  total_amount: number | null;
  currency: string | null;
  elapsed_minutes: number | null;
  explanation: string;
}

export interface NetworkView {
  case_id: string;
  agent3_status: string;
  sender_account_id: string | null;
  receiver_account_id: string | null;
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  findings: NetworkFinding[];
  truncated: boolean;
  total_edges: number;
  agent3_warnings: string[];
  note: string;
}
