import { api } from "./api";

function keyToBytes(base64url: string) {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function currentSubscription() {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.getRegistration("/app/");
  return reg ? reg.pushManager.getSubscription() : null;
}

/** Ask permission, subscribe this browser and register it with the server. */
export async function enablePush(): Promise<string | null> {
  const { enabled, public_key } = await api.get<{ enabled: boolean; public_key: string | null }>("/api/v1/push/key");
  if (!enabled || !public_key) return "Push notifications aren't set up on this site yet.";
  if (!pushSupported()) return "This browser doesn't support push notifications. On iPhone, add the site to your home screen first.";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "Notifications are blocked for this site in your browser settings.";
  const reg = await navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" });
  await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyToBytes(public_key) });
  await api.post("/api/v1/push/subscribe", sub.toJSON());
  return null;
}

export async function disablePush() {
  const sub = await currentSubscription();
  if (!sub) return;
  await api.post("/api/v1/push/unsubscribe", { endpoint: sub.endpoint });
  await sub.unsubscribe();
}
