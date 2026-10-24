/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: ["class", '[data-theme="chatchimie-dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Source Sans 3", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        heading: ["Lexend", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      animation: {
        "fade-in": "fadeIn 0.35s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
        "pulse-slow": "pulse 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "float-slow": "float 9s ease-in-out infinite",
        "float-slower": "float 13s ease-in-out infinite",
        "shimmer": "shimmer 3.5s linear infinite",
        "pulse-ring": "pulseRing 2.4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: 0 },
          "100%": { opacity: 1 },
        },
        slideUp: {
          "0%": { opacity: 0, transform: "translateY(8px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(2%, -4%) scale(1.05)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
        },
        pulseRing: {
          "0%": { transform: "scale(0.85)", opacity: 0.6 },
          "70%": { transform: "scale(1.25)", opacity: 0 },
          "100%": { transform: "scale(0.85)", opacity: 0 },
        },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(159,18,57,0.15), 0 8px 24px -8px rgba(159,18,57,0.35)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography"), require("daisyui")],
  daisyui: {
    themes: [
      {
        "chatchimie-light": {
          primary: "#9f1239",
          "primary-content": "#ffffff",
          secondary: "#b45309",
          "secondary-content": "#ffffff",
          accent: "#d97706",
          "accent-content": "#ffffff",
          neutral: "#1f2937",
          "base-100": "#ffffff",
          "base-200": "#fbf4f5",
          "base-300": "#f3e3e6",
          info: "#0369a1",
          success: "#16a34a",
          warning: "#d97706",
          error: "#dc2626",
        },
      },
      {
        "chatchimie-dark": {
          primary: "#fb7185",
          "primary-content": "#2a0610",
          secondary: "#fbbf24",
          "secondary-content": "#2b1a04",
          accent: "#fbbf24",
          "accent-content": "#2b1a04",
          neutral: "#e5e7eb",
          "base-100": "#160b0e",
          "base-200": "#1f1014",
          "base-300": "#33191f",
          info: "#38bdf8",
          success: "#4ade80",
          warning: "#fbbf24",
          error: "#f87171",
        },
      },
    ],
    darkTheme: "chatchimie-dark",
  },
}
