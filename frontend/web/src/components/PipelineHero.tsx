import { useEffect, useState } from "react";
import { Terminal, FileText, Play, ShieldCheck } from "lucide-react";

const steps = [
  { icon: Terminal, label: "Prompt", color: "text-aureum-gold" },
  { icon: FileText, label: "YAML", color: "text-aureum-gold-soft" },
  { icon: Play, label: "Backtest", color: "text-aureum-gold" },
  { icon: ShieldCheck, label: "Certificate", color: "text-aureum-success" },
];

export default function PipelineHero() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setActive((prev) => (prev + 1) % steps.length);
    }, 1200);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="w-full max-w-4xl mx-auto">
      <div className="flex items-center justify-between gap-2 md:gap-4">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const isActive = index <= active;
          const isCurrent = index === active;
          return (
            <div key={step.label} className="flex-1 flex flex-col items-center">
              <div
                className={`
                  relative flex items-center justify-center w-12 h-12 md:w-16 md:h-16 rounded-full border
                  transition-all duration-500
                  ${
                    isActive
                      ? "border-aureum-gold bg-aureum-gold/10 shadow-[0_0_20px_rgba(201,162,39,0.25)]"
                      : "border-aureum-muted bg-aureum-panel"
                  }
                `}
              >
                <Icon
                  className={`w-5 h-5 md:w-6 md:h-6 transition-colors duration-500 ${
                    isActive ? step.color : "text-aureum-muted"
                  }`}
                />
                {isCurrent && (
                  <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-aureum-gold animate-pulse-slow" />
                )}
              </div>
              <span
                className={`mt-3 text-xs md:text-sm font-medium transition-colors duration-500 ${
                  isActive ? "text-aureum-cream" : "text-aureum-muted"
                }`}
              >
                {step.label}
              </span>

              {index < steps.length - 1 && (
                <div className="absolute left-0 right-0 top-8 md:top-10 -z-10 px-8 md:px-12">
                  {/* connector handled via parent flex; no absolute needed */}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Connecting lines */}
      <div className="hidden md:flex items-center justify-between -mt-14 px-16">
        {steps.slice(0, -1).map((_, index) => {
          const filled = index < active;
          return (
            <div key={index} className="flex-1 h-px mx-2">
              <div
                className={`h-full transition-all duration-700 ${
                  filled ? "bg-aureum-gold" : "bg-aureum-muted/40"
                }`}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
