import createClient from 'openapi-fetch'
import type { paths } from './schema'

// Same-origin by default: dev uses the Vite proxy (vite.config.ts), production
// uses VITE_API_URL. Types come from the generated schema — never hand-written.
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? '/',
})
