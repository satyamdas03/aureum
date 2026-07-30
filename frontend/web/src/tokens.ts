/**
 * Aureum Design Tokens
 *
 * Based on the Stitch-generated "Deep Space" Material 3 design system.
 * Surface: dark olive/navy backgrounds. Primary: luminous Aureum Gold.
 */

export const colors = {
  // Canvas & surfaces
  background: "#14140f",
  surface: "#14140f",
  "surface-dim": "#14140f",
  "surface-bright": "#3a3933",
  "surface-container-lowest": "#0f0e0a",
  "surface-container-low": "#1c1c16",
  "surface-container": "#20201a",
  "surface-container-high": "#2b2a24",
  "surface-container-highest": "#36352f",
  "surface-variant": "#36352f",

  // Legacy aliases still used in some components
  ink: "#0B0F19",
  panel: "#111827",
  card: "#1A2233",

  // Content colors
  "on-surface": "#e6e2d9",
  "on-surface-variant": "#d1c5af",
  "inverse-surface": "#e6e2d9",
  "inverse-on-surface": "#31302b",
  outline: "#99907b",
  "outline-variant": "#4d4635",

  // Primary (Aureum Gold)
  primary: "#ecc246",
  "on-primary": "#3d2e00",
  "primary-container": "#c9a227",
  "on-primary-container": "#4b3a00",
  "inverse-primary": "#755b00",
  "surface-tint": "#ecc246",
  "primary-fixed": "#ffe08e",
  "primary-fixed-dim": "#ecc246",
  "on-primary-fixed": "#241a00",
  "on-primary-fixed-variant": "#584400",

  // Secondary
  secondary: "#c0c6db",
  "on-secondary": "#293040",
  "secondary-container": "#404758",
  "on-secondary-container": "#aeb5c9",
  "secondary-fixed": "#dce2f7",
  "secondary-fixed-dim": "#c0c6db",
  "on-secondary-fixed": "#141b2b",
  "on-secondary-fixed-variant": "#404758",

  // Tertiary
  tertiary: "#bec6dd",
  "on-tertiary": "#283042",
  "tertiary-container": "#9ea6bc",
  "on-tertiary-container": "#343c4e",
  "tertiary-fixed": "#dae2fa",
  "tertiary-fixed-dim": "#bec6dd",
  "on-tertiary-fixed": "#131b2c",
  "on-tertiary-fixed-variant": "#3f4759",

  // Error
  error: "#ffb4ab",
  "on-error": "#690005",
  "error-container": "#93000a",
  "on-error-container": "#ffdad6",

  // Legacy semantic aliases
  gold: "#C9A227",
  "gold-soft": "#D4B85A",
  cream: "#F5F1E8",
  slate: "#8A91A8",
  muted: "#5B6275",
  success: "#22C55E",
  danger: "#EF4444",
  warning: "#F59E0B",
};

export const fonts = {
  display: "Literata, Crimson Pro, Georgia, serif",
  sans: "Inter, system-ui, sans-serif",
  mono: "JetBrains Mono, monospace",
};

export const fontSizes = {
  "hero-lg": ["72px", { lineHeight: "84px", letterSpacing: "-0.02em", fontWeight: "600" }],
  "hero-lg-mobile": ["48px", { lineHeight: "56px", fontWeight: "600" }],
  h1: ["48px", { lineHeight: "56px", fontWeight: "500" }],
  "h1-mobile": ["32px", { lineHeight: "40px", fontWeight: "500" }],
  h2: ["32px", { lineHeight: "40px", fontWeight: "500" }],
  "body-lg": ["16px", { lineHeight: "24px", fontWeight: "400" }],
  "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
  "mono-label": ["13px", { lineHeight: "16px", letterSpacing: "0.02em", fontWeight: "500" }],
  "mono-data": ["12px", { lineHeight: "16px", fontWeight: "400" }],
};

export const radius = {
  sm: "0.125rem", // 2px
  DEFAULT: "0.25rem", // 4px
  md: "0.375rem", // 6px
  lg: "0.5rem", // 8px
  xl: "0.75rem", // 12px
  full: "9999px",
};

export const spacing = {
  unit: "4px",
  xs: "4px",
  sm: "8px",
  md: "16px",
  lg: "24px",
  xl: "48px",
  gutter: "16px",
  "margin-mobile": "16px",
  "margin-desktop": "32px",
  "container-max": "1280px",
};

export const shadows = {
  // Design system avoids physical shadows; only subtle glow for verified states.
  certificate: "0 0 15px rgba(201, 162, 39, 0.05)",
};
