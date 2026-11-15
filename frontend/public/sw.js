/* Campus Retain service worker: shows push notifications and opens the app on click.
   It does not cache pages or data. */
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: "Campus Retain", body: event.data && event.data.text() }; }
  const url = typeof data.url === "string" && data.url.startsWith("/app/") ? data.url : "/app/";
  event.waitUntil(self.registration.showNotification(data.title || "Campus Retain", {
    body: data.body || "", data: { url }, tag: url, icon: "/static/no-image.svg",
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/app/";
  event.waitUntil((async () => {
    const tabs = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const tab of tabs) {
      if (new URL(tab.url).pathname.startsWith("/app/")) { await tab.focus(); return tab.navigate(url); }
    }
    return self.clients.openWindow(url);
  })());
});
