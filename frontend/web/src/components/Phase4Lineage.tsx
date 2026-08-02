import { useState } from "react";
import { ChevronDown, ChevronUp, Fingerprint, Network, ShieldAlert, BrainCircuit, BarChart3 } from "lucide-react";
import type { Certificate } from "../types";

function Hash({ value, label }: { value?: string; label: string }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono-label text-[10px] text-slate uppercase">{label}</span>
      <span className="font-mono-data text-[10px] text-cream break-all" title={value}>
        {value.slice(0, 16)}…
      </span>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-card bg-ink rounded p-sm space-y-2">
      <div className="flex items-center gap-2 text-cream font-semibold text-xs">
        <Icon className="w-4 h-4 text-aureum-gold" />
        {title}
      </div>
      {children}
    </div>
  );
}

export default function Phase4Lineage({ certificate }: { certificate: Certificate }) {
  const [open, setOpen] = useState(true);
  const pc = certificate.portfolio_construction;
  const alpha = certificate.alpha_lineage;
  const graph = certificate.knowledge_graph;
  const es = certificate.economic_security;

  return (
    <div className="border border-card bg-panel rounded p-sm">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between text-cream font-semibold text-sm"
      >
        <span className="flex items-center gap-2">
          <Fingerprint className="w-4 h-4 text-aureum-gold" />
          Phase 4 Lineage
        </span>
        {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          {pc && (
            <Section icon={BarChart3} title="Portfolio Construction">
              <div className="grid grid-cols-2 gap-2 font-mono-data text-[11px] text-slate">
                <p>
                  <span className="text-on-surface-variant">objective:</span> {pc.objective}
                </p>
                <p>
                  <span className="text-on-surface-variant">risk:</span> {pc.risk_measure}
                </p>
                <p>
                  <span className="text-on-surface-variant">cov:</span> {pc.covariance_estimator}
                </p>
                <p>
                  <span className="text-on-surface-variant">rf:</span> {pc.risk_free_rate}
                </p>
              </div>
              {typeof pc.coverage_level === "number" && (
                <p className="font-mono-data text-[11px] text-slate">
                  <span className="text-on-surface-variant">conformal coverage:</span>{" "}
                  {(pc.coverage_level * 100).toFixed(1)}%
                  {typeof pc.prediction_set_width === "number" && (
                    <span> · width {(pc.prediction_set_width * 100).toFixed(2)}%</span>
                  )}
                </p>
              )}
              <div className="grid grid-cols-2 gap-2">
                <Hash value={pc.optimization_inputs_hash} label="Optimization Inputs" />
                <Hash value={pc.calibration_set_hash} label="Calibration Set" />
                <Hash value={pc.causal_graph_hash} label="Causal Graph" />
                <Hash value={pc.conditional_covariance_hash} label="Conditional Cov" />
                <Hash value={pc.model_architecture_hash} label="Model Arch" />
                <Hash value={pc.weights_hash} label="Model Weights" />
              </div>
            </Section>
          )}

          {alpha && alpha.alpha_signals.length > 0 && (
            <Section icon={BrainCircuit} title="Neuro-Symbolic Alpha">
              {alpha.alpha_signals.map((sig) => (
                <div key={sig.name} className="space-y-1">
                  <p className="font-mono-data text-[11px] text-cream">{sig.name}</p>
                  <p className="font-mono-data text-[10px] text-slate break-all">{sig.formula}</p>
                  <p className="font-mono-data text-[10px] text-slate">
                    safety: {sig.safety_checks_passed ? "PASS" : "FAIL"}
                    {sig.llm_model ? ` · ${sig.llm_model}` : ""}
                  </p>
                </div>
              ))}
            </Section>
          )}

          {(graph || certificate.graph_node_id) && (
            <Section icon={Network} title="Semantic Knowledge Graph">
              <Hash value={certificate.graph_node_id} label="Graph Node" />
              {certificate.linked_entity_hashes && certificate.linked_entity_hashes.length > 0 && (
                <p className="font-mono-data text-[11px] text-slate">
                  linked entities: {certificate.linked_entity_hashes.length}
                </p>
              )}
              {graph && (
                <p className="font-mono-data text-[11px] text-slate">
                  total entities: {graph.entities.length}
                </p>
              )}
            </Section>
          )}

          {es && (
            <Section icon={ShieldAlert} title="Economic Security Audit">
              <p className="font-mono-data text-[11px] text-slate">
                enabled: {es.enabled ? "YES" : "NO"}
                {es.attack_vectors ? ` · vectors: ${es.attack_vectors.join(", ")}` : ""}
              </p>
              <Hash value={es.replay_inputs_hash} label="Replay Inputs" />
            </Section>
          )}

          {certificate.determinism?.economic_security_hash && (
            <Hash value={certificate.determinism.economic_security_hash} label="EconSec Determinism Hash" />
          )}
        </div>
      )}
    </div>
  );
}
