/**
 * Session helpers.
 *
 * For now (pre-auth) we generate a stable UUID per browser session stored in
 * sessionStorage.  When you add real auth, replace `getSessionId` with a call
 * to your auth provider (e.g. `supabase.auth.getUser()`) and use the user's ID.
 */

function generateUUID(): string {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID()
    }
    // Fallback for older environments
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === "x" ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
  }
  
  /**
   * Returns a stable session ID for the current browser session.
   * Replace this with your auth user ID when login is implemented.
   */
  export function getSessionId(): string {
    if (typeof window === "undefined") return "ssr-placeholder"
  
    const key = "mds_session_id"
    let id = sessionStorage.getItem(key)
    if (!id) {
      id = generateUUID()
      sessionStorage.setItem(key, id)
    }
    return id
  }
  
  /**
   * Builds a connector-scoped session ID so each pipeline setup is independent.
   * e.g.  "uuid-v1_meta"
   */
  export function getConnectorSessionId(connectorId: string): string {
    return `${getSessionId()}-${connectorId}`
  }