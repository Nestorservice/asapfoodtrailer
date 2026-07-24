/* ═══════════════════════════════════════════════════
   ASAP FOOD TRAILER — ADMIN GLOBAL SCRIPT & PWA MANAGER
   Handles App Badging, Sound Notifications & Bottom Nav
   ═══════════════════════════════════════════════════ */

window.AdminGlobal = (function() {
    let currentUnread = 0;
    let audioCtx = null;
    let notifSound = null;

    try {
        notifSound = new Audio('/assets/audio/notification.wav');
        notifSound.preload = 'auto';
    } catch(e) {}

    // Unlock Audio Context on first user interaction
    function unlockAudio() {
        if (notifSound) {
            notifSound.play().then(() => {
                notifSound.pause();
                notifSound.currentTime = 0;
            }).catch(() => {});
        }
        try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (AC && !audioCtx) {
                audioCtx = new AC();
                if (audioCtx.state === 'suspended') audioCtx.resume();
            }
        } catch(e) {}
        document.removeEventListener('click', unlockAudio);
        document.removeEventListener('touchstart', unlockAudio);
    }
    document.addEventListener('click', unlockAudio, { once: true });
    document.addEventListener('touchstart', unlockAudio, { once: true });

    function playSound() {
        if (notifSound) {
            notifSound.currentTime = 0;
            const p = notifSound.play();
            if (p && typeof p.then === 'function') {
                p.catch(() => playSynthesizedChime());
                return;
            }
        }
        playSynthesizedChime();
    }

    function playSynthesizedChime() {
        try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            const ctx = audioCtx || new AC();
            if (ctx.state === 'suspended') ctx.resume();

            const now = ctx.currentTime;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'sine';
            osc.frequency.setValueAtTime(587.33, now); // D5
            osc.frequency.setValueAtTime(880.00, now + 0.12); // A5

            gain.gain.setValueAtTime(0, now);
            gain.gain.linearRampToValueAtTime(0.35, now + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.start(now);
            osc.stop(now + 0.5);
        } catch(e) {}
    }

    function updateBadge(count) {
        currentUnread = count || 0;

        // 1. PWA App Icon Badge (Home Screen / Taskbar)
        if ('setAppBadge' in navigator) {
            if (currentUnread > 0) {
                navigator.setAppBadge(currentUnread).catch(() => {});
            } else {
                navigator.clearAppBadge().catch(() => {});
            }
        } else if ('setExperimentalAppBadge' in navigator) {
            if (currentUnread > 0) {
                navigator.setExperimentalAppBadge(currentUnread).catch(() => {});
            } else {
                navigator.clearExperimentalAppBadge().catch(() => {});
            }
        }

        // 2. Mobile Nav Bar Badge
        const badges = document.querySelectorAll('#mobileNavChatBadge, .mobile-nav-badge');
        badges.forEach(b => {
            if (currentUnread > 0) {
                b.textContent = currentUnread > 99 ? '99+' : currentUnread;
                b.style.display = 'inline-flex';
            } else {
                b.style.display = 'none';
            }
        });

        // 3. Document Title
        if (currentUnread > 0) {
            const cleanTitle = document.title.replace(/^\(\d+\)\s*/, '');
            document.title = `(${currentUnread}) ${cleanTitle}`;
        } else {
            document.title = document.title.replace(/^\(\d+\)\s*/, '');
        }
    }

    // Automatic PWA Service Worker Registration & Live Auto-Update
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function() {
            navigator.serviceWorker.register('/assets/js/sw.js').then(function(reg) {
                // Force check for updates from server on every visit
                reg.update();
            }).catch(function(err) {
                console.log('[PWA] Service worker registration error:', err);
            });
        });

        // Auto-refresh UI when new Service Worker version activates
        let isRefreshing = false;
        navigator.serviceWorker.addEventListener('controllerchange', function() {
            if (!isRefreshing) {
                isRefreshing = true;
                window.location.reload();
            }
        });
    }

    // Automatic Unread Badge Polling every 5 seconds
    function pollUnread() {
        fetch('/api/admin/unread_count')
            .then(r => r.json())
            .then(data => {
                if (data && typeof data.unread === 'number') {
                    updateBadge(data.unread);
                }
            })
            .catch(() => {});
    }

    document.addEventListener('DOMContentLoaded', function() {
        pollUnread();
        setInterval(pollUnread, 5000);
    });

    return {
        updateBadge: updateBadge,
        playSound: playSound,
        playChime: playSynthesizedChime
    };
})();
