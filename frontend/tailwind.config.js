/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          bg: "#0A0A0F",
          surface: "#13131A",
          border: "#1E1E2A",
          muted: "#8B8BA3",
          accent: "#7C5CFC",
          "accent-hover": "#6A4AE8",
          success: "#22C55E",
          danger: "#EF4444",
          warning: "#F59E0B",
        },
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "sans-serif"],
        display: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"],
      },
      animation: {
        shimmer: "shimmer 2s ease-in-out infinite",
        pulse_slow: "pulse 3s ease-in-out infinite",
      },
      keyframes: {
        shimmer: {
          "0%, 100%": { opacity: 0.4 },
          "50%": { opacity: 0.8 },
        },
      },
    },
  },
  plugins: [],
};
