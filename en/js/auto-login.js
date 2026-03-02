export async function autoLoginFromFragment(auth, signInWithCustomToken, paramName = "ct") {
  try {
    const rawHash = window.location.hash || "";
    if (!rawHash || rawHash === "#") return;

    const params = new URLSearchParams(rawHash.startsWith("#") ? rawHash.slice(1) : rawHash);
    const token = params.get(paramName);
    if (!token) return;

    if (!auth?.currentUser) {
      await signInWithCustomToken(auth, token);
    }
  } catch (e) {
    console.warn("Auto-login failed", e);
  } finally {
    try {
      const rawHash = window.location.hash || "";
      const params = new URLSearchParams(rawHash.startsWith("#") ? rawHash.slice(1) : rawHash);
      params.delete(paramName);
      const nextHash = params.toString();

      const u = new URL(window.location.href);
      u.hash = nextHash ? `#${nextHash}` : "";
      window.history.replaceState({}, document.title, u.pathname + u.search + u.hash);
    } catch (_) {}
  }
}

