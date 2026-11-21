/** Configuración de Tailwind CSS para AeroVigía. */
module.exports = {
  content: [
    "./gestion/templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ['"Space Grotesk"', "Inter", "sans-serif"],
      },
      colors: {
        radar: {
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
        },
      },
      boxShadow: {
        glow: "0 0 40px -12px rgba(34, 211, 238, 0.45)",
      },
    },
  },
  plugins: [],
};
