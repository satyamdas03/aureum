/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        aureum: {
          ink: "#0B0F19",
          panel: "#111827",
          card: "#1A2233",
          gold: "#C9A227",
          "gold-soft": "#D4B85A",
          cream: "#F5F1E8",
          slate: "#8A91A8",
          muted: "#5B6275",
          success: "#22C55E",
          danger: "#EF4444",
          warning: "#F59E0B",
        },
      },
      fontFamily: {
        display: ["Crimson Pro", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "flow": "flow 2s ease-in-out infinite",
      },
      keyframes: {
        flow: {
          "0%, 100%": { opacity: "0.4", transform: "translateX(0)" },
          "50%": { opacity: "1", transform: "translateX(4px)" },
        },
      },
    },
  },
  plugins: [],
};
