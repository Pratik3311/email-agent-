import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#F2EEE3",
        paper: "#FAF8F1",
        ink: "#111111",
        accent: "#E4FF3F",
      },
      boxShadow: {
        brutal: "4px 4px 0 0 #111111",
        "brutal-sm": "3px 3px 0 0 #111111",
        "brutal-lg": "6px 6px 0 0 #111111",
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
