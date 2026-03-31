/* ─── ASAP Food Trailer — Service Worker ─── */
/* Handles push notifications when the admin is offline */

const CACHE_NAME = 'asap-admin-v1';
const NOTIFICATION_SOUND_URL = '/assets/audio/notification.mp3';

// Install
self.addEventListener('install', event => {
    self.skipWaiting();
    // Pre-cache notification sound
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll([NOTIFICATION_SOUND_URL]).catch(() => {});
        })
    );
});

// Activate
self.addEventListener('activate', event => {
    event.waitUntil(self.clients.claim());
});

// Push notification received
self.addEventListener('push', event => {
    let data = { title: 'New Message', body: 'You have a new message', icon: '/assets/img/logo/logo.jpg' };
    
    try {
        if (event.data) {
            const payload = event.data.json();
            data = {
                title: payload.title || 'New Message — ASAP',
                body: payload.body || 'You have a new message',
                icon: payload.icon || '/assets/img/logo/logo.jpg',
                badge: '/assets/img/logo/favicon.svg',
                tag: payload.tag || 'asap-chat-' + Date.now(),
                data: {
                    url: payload.url || '/admin/chat',
                    channelId: payload.channelId || ''
                },
                vibrate: [200, 100, 200, 100, 200],
                requireInteraction: true,
                actions: [
                    { action: 'reply', title: '💬 Reply' },
                    { action: 'dismiss', title: 'Dismiss' }
                ]
            };
        }
    } catch (e) {
        console.error('[SW] Push parse error:', e);
    }

    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: data.icon,
            badge: data.badge || '/assets/img/logo/favicon.svg',
            tag: data.tag,
            data: data.data,
            vibrate: data.vibrate || [200, 100, 200],
            requireInteraction: data.requireInteraction !== false,
            actions: data.actions || [],
            silent: false
        })
    );
});

// Notification click
self.addEventListener('notificationclick', event => {
    event.notification.close();

    const url = event.notification.data?.url || '/admin/chat';

    if (event.action === 'dismiss') return;

    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
            // Focus existing admin chat tab if open
            for (const client of clients) {
                if (client.url.includes('/admin/chat')) {
                    return client.focus();
                }
            }
            // Otherwise open new tab
            return self.clients.openWindow(url);
        })
    );
});
