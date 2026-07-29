import { defineCloudflareConfig } from '@opennextjs/cloudflare'
import staticAssetsIncrementalCache from '@opennextjs/cloudflare/overrides/incremental-cache/static-assets-incremental-cache'

export default defineCloudflareConfig({
  // This project only serves build-time prerendered pages; it does not use ISR.
  // Package the prerender cache with Worker assets so dynamic SSG routes work
  // without requiring R2 to be enabled on the Cloudflare account.
  incrementalCache: staticAssetsIncrementalCache,
})
