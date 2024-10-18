import globals from "globals";
import pluginJs from "@eslint/js";
import googleConfig from "eslint-config-google";
export default [
  { languageOptions: { globals: globals.browser } },
  pluginJs.configs.recommended,
  googleConfig,
];
