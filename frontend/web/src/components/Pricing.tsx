import { Link } from "react-router-dom";
import { ArrowRight, Check } from "lucide-react";
import AureumLogo from "./AureumLogo";

const plans = [
  {
    name: "Solo",
    price: "$0",
    period: "forever",
    description: "Open source, self-hosted, fully functional.",
    cta: "Get started",
    ctaTo: "/dashboard",
    features: [
      "Natural-language strategy authoring",
      "Backtest certificates + SHA-256 lineage",
      "4 built-in ranking signals",
      "Alpaca snapshot adapter",
      "SMT-LIB / Lean 4 verifier bridge",
      "Community support (GitHub issues)",
    ],
  },
  {
    name: "Team",
    price: "$49",
    period: "per user / month",
    description: "For quant teams sharing strategies and data.",
    cta: "Coming soon",
    ctaTo: "#",
    highlight: true,
    features: [
      "Everything in Solo",
      "Shared workspace + versioned strategies",
      "Private data connectors",
      "Slack / email anomaly alerts",
      "Role-based access control",
      "Priority email support",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "annual contract",
    description: "Deploy Aureum inside your compliance perimeter.",
    cta: "Contact us",
    ctaTo: "mailto:satyamdas03@gmail.com",
    features: [
      "Everything in Team",
      "On-premise or VPC deployment",
      "SSO / SAML / SCIM",
      "Audit-grade lineage reports",
      "Custom verifier plugins",
      "Dedicated support channel",
    ],
  },
];

export default function Pricing() {
  return (
    <div className="min-h-screen bg-surface text-on-surface">
      {/* Nav */}
      <nav className="border-b border-card">
        <div className="max-w-container-max mx-auto px-margin-desktop py-4 flex items-center justify-between">
          <Link to="/">
            <AureumLogo showWordmark size={32} />
          </Link>
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-bold text-deep-navy bg-aureum-gold hover:bg-primary transition-colors rounded-md"
          >
            Open Dashboard
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>

      {/* Heading */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-aureum-gold/5 via-transparent to-transparent" />
        <div className="relative max-w-container-max mx-auto px-margin-desktop pt-16 pb-10 text-center">
          <p className="inline-block px-3 py-1 mb-4 text-xs font-semibold tracking-wider uppercase text-aureum-gold border border-aureum-gold/30 rounded-full">
            Pricing
          </p>
          <h1 className="font-h2 text-h2 text-cream mb-4">
            Start free, scale with trust
          </h1>
          <p className="text-slate text-lg max-w-2xl mx-auto">
            Solo is fully open source. Team and Enterprise add collaboration,
            governance, and support when you need it.
          </p>
        </div>
      </section>

      {/* Plans */}
      <section className="max-w-container-max mx-auto px-margin-desktop pb-24">
        <div className="grid md:grid-cols-3 gap-8">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`relative p-6 md:p-8 flex flex-col border ${
                plan.highlight
                  ? "bg-card border-aureum-gold"
                  : "bg-panel/30 border-card"
              }`}
            >
              {plan.highlight && (
                <span className="absolute -top-3 left-6 px-3 py-1 text-xs font-bold tracking-wider uppercase text-deep-navy bg-aureum-gold rounded-sm"
                >
                  Recommended
                </span>
              )}
              <h2 className="font-h2 text-2xl font-medium text-cream">
                {plan.name}
              </h2>
              <p className="text-slate text-sm mt-2 mb-6">
                {plan.description}
              </p>
              <div className="mb-6">
                <span className="font-h2 text-4xl font-medium text-cream">
                  {plan.price}
                </span>
                <span className="text-muted ml-2">/{plan.period}</span>
              </div>
              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-3">
                    <div className="mt-0.5 w-5 h-5 rounded-full bg-aureum-gold/10 flex items-center justify-center shrink-0"
                    >
                      <Check className="w-3 h-3 text-aureum-gold" />
                    </div>
                    <span className="text-cream text-sm">{feature}</span>
                  </li>
                ))}
              </ul>
              <Link
                to={plan.ctaTo}
                className={`w-full text-center inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-md font-bold transition-colors ${
                  plan.highlight
                    ? "text-deep-navy bg-aureum-gold hover:bg-primary"
                    : "text-cream border border-card hover:border-aureum-gold"
                }`}
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>

        {/* FAQ / note */}
        <div className="mt-16 max-w-3xl mx-auto text-center">
          <p className="text-slate text-sm">
            Team and Enterprise tiers are on the roadmap. Right now, everything
            in Solo is available in the open-source repository. If your org needs
            a private deployment or compliance review, email{" "}
            <a
              href="mailto:satyamdas03@gmail.com"
              className="text-aureum-gold hover:underline"
            >
              satyamdas03@gmail.com
            </a>
            .
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-card bg-panel/30">
        <div className="max-w-container-max mx-auto px-margin-desktop py-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-slate text-sm">
            © {new Date().getFullYear()} Aureum. Open source under Apache-2.0.
          </p>
          <div className="flex items-center gap-6">
            <Link
              to="/"
              className="text-aureum-gold hover:text-primary text-sm"
            >
              ← Back home
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
