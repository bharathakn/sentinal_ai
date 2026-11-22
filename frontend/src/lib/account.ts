// Remembers only that this browser has had an account, to open the right sign-in tab.
const KEY = "sentinel.hasAccount";

export function hasAccountHere(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false; // storage blocked: show "Create account", with "Sign in" one click away
  }
}

export function rememberAccount() {
  try {
    localStorage.setItem(KEY, "1");
  } catch {
    // Storage blocked: only the default tab is affected.
  }
}
