/* eslint-disable @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-call, @typescript-eslint/no-unsafe-member-access */

import globals from "globals";
import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import importPlugin from "eslint-plugin-import";
import { fileURLToPath } from "url";
import { dirname } from "path";
import { FlatCompat } from "@eslint/eslintrc";
import stylistic from "@stylistic/eslint-plugin";

const compat = new FlatCompat({
  baseDirectory: dirname(fileURLToPath(import.meta.url)),
});

export default [
  ...compat.config({
    parserOptions: {
      ecmaVersion: "latest",
      project: ["tsconfig(.*)?.json"]
    }
  }),
  {
    languageOptions: { globals: globals.browser },
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    files: ["**/*.ts", "**/*.tsx"],
    plugins: {
      import: importPlugin,
      stylistic,
    },
    rules: {
      indent: [
        "error",
        2
      ],
      "linebreak-style": 0,
      quotes: [
        "error",
        "double"
      ],
      semi: [
        "error",
        "always"
      ],
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-unused-vars": [
        "error", { argsIgnorePattern: "^_" }
      ],
      "no-empty": [2, { allowEmptyCatch: true }],
      "@typescript-eslint/no-misused-promises": [
        "error",
        {
          checksVoidReturn: false
        }
      ],
      "import/order": [
        "error",
        {
          alphabetize: {
            caseInsensitive: true,
            order: "asc",
          },
          groups: ["external", "builtin", "parent", ["sibling", "index"]],
          "newlines-between": "never",
          pathGroups: [
            {
              group: "external",
              pattern: "react",
              position: "before",
            },
            {
              group: "external",
              pattern: "@my_org/**",
              position: "after",
            },
          ],
          pathGroupsExcludedImportTypes: ["builtin"],
        },
      ],
      "stylistic/max-len": [
        "error", 
        { 
          ignoreTemplateLiterals: true, 
          code: 100, 
          ignoreComments: true, 
          ignoreStrings: true 
        }
      ],
      "stylistic/object-curly-spacing": [
        "error",
        "always"
      ]
    },
  },
];