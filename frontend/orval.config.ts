import { defineConfig } from "orval";

export default defineConfig({
  api: {
    input: "http://localhost:8000/openapi.json",
    output: {
      mode: "tags-split",
      target: "src/api/generated",
      schemas: "src/api/generated/schemas",
      client: "react-query",
      httpClient: "fetch",
      mock: {
        generators: [{ type: "msw" }],
      },
      override: {
        mutator: {
          path: "src/api/fetch-client.ts",
          name: "fetchClient",
        },
      },
    },
  },
});
