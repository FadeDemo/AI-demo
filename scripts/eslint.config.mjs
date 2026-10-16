import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ...js.configs.recommended,
    files: ["scripts/cursor-helper/*.js", "scripts/eslint.config.mjs"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["scripts/cursor-helper/*.js"],
    languageOptions: { sourceType: "commonjs" },
  },
];
