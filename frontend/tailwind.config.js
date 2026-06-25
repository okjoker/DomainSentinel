/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0a0e16",
          900: "#0f1623",
          800: "#162032",
          700: "#1e2c44",
          600: "#2a3b59",
        },
      },
    },
  },
  plugins: [],
};
