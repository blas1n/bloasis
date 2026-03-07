import createClient from "openapi-fetch";
import type { paths } from "./generated/api-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api";

const client = createClient<paths>({
  baseUrl: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export default client;
