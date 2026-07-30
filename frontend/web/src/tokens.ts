/**
 * Aureum design tokens.
 *
 * This file is the single source of truth for the visual identity used across
 * the landing page, dashboard, and any future surfaces. Values are mirrored in
 * tailwind.config.js for utility classes.
 */

export const colors = {
  ink: "#0B0F19",
  panel: "#111827",
  card: "#1A2233",
  gold: "#C9A227",
  goldSoft: "#D4B85A",
  goldGlow: "rgba(201, 162, 39, 0.15)",
  cream: "#F5F1E8",
  slate: "#8A91A8",
  muted: "#5B6275",
  success: "#22C55E",
  danger: "#EF4444",
  warning: "#F59E0B",
} as const;

export const fonts = {
  display: "Crimson Pro, Georgia, serif",
  sans: "Inter, system-ui, sans-serif",
  mono: "JetBrains Mono, monospace",
} as const;

export const radius = {
  button: "6px",
  card: "6px",
  input: "4px",
} as const;

export const spacing = {
  xs: "4px",
  sm: "8px",
  md: "16px",
  lg: "24px",
  xl: "32px",
  xxl: "48px",
  hero: "96px",
} as const;

export const maxWidth = "1280px";
