/* ═══════════════════════════════════════════════════
   ASAP FOOD TRAILER — App JavaScript
   Core interactions, sliders, animations
   ═══════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', function () {

    // ─── AOS (Animate on Scroll) ───
    if (typeof AOS !== 'undefined') {
        AOS.init({
            duration: 800,
            once: true,
            offset: 60,
            easing: 'ease-out-cubic',
        });
    }

    // ─── STICKY HEADER ───
    var header = document.getElementById('vl-header-sticky');
    if (header) {
        var lastScroll = 0;
        window.addEventListener('scroll', function () {
            var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            if (scrollTop > 80) {
                header.classList.add('sticky');
            } else {
                header.classList.remove('sticky');
            }
            lastScroll = scrollTop;
        }, { passive: true });
    }

    // ─── MOBILE MENU ───
    var offcanvasToggle = document.querySelector('.vl-offcanvas-toggle');
    var offcanvas = document.querySelector('.vl-offcanvas');
    var offcanvasClose = document.querySelector('.vl-offcanvas-close-toggle');
    var offcanvasOverlay = document.querySelector('.vl-offcanvas-overlay');

    function openMobileMenu() {
        if (offcanvas) offcanvas.classList.add('vl-offcanvas-open');
        if (offcanvasOverlay) offcanvasOverlay.classList.add('vl-offcanvas-overlay-open');
        document.body.style.overflow = 'hidden';
    }

    function closeMobileMenu() {
        if (offcanvas) offcanvas.classList.remove('vl-offcanvas-open');
        if (offcanvasOverlay) offcanvasOverlay.classList.remove('vl-offcanvas-overlay-open');
        document.body.style.overflow = '';
    }

    if (offcanvasToggle) offcanvasToggle.addEventListener('click', openMobileMenu);
    if (offcanvasClose) offcanvasClose.addEventListener('click', closeMobileMenu);
    if (offcanvasOverlay) offcanvasOverlay.addEventListener('click', closeMobileMenu);

    // Close mobile menu on link click
    var mobileLinks = document.querySelectorAll('.vl-offcanvas-menu a');
    mobileLinks.forEach(function (link) {
        link.addEventListener('click', closeMobileMenu);
    });

    // ─── COUNTER ANIMATION ───
    var counters = document.querySelectorAll('.counter');
    if (counters.length > 0) {
        var counterObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    var el = entry.target;
                    var target = parseInt(el.getAttribute('data-count')) || 0;
                    var duration = 2000;
                    var start = 0;
                    var startTime = null;

                    function animate(timestamp) {
                        if (!startTime) startTime = timestamp;
                        var progress = Math.min((timestamp - startTime) / duration, 1);
                        var eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
                        el.textContent = Math.floor(eased * target);
                        if (progress < 1) {
                            requestAnimationFrame(animate);
                        } else {
                            el.textContent = target;
                        }
                    }
                    requestAnimationFrame(animate);
                    counterObserver.unobserve(el);
                }
            });
        }, { threshold: 0.5 });

        counters.forEach(function (c) { counterObserver.observe(c); });
    }

    // ─── PHONE NUMBER FORMATTING ───
    var phoneInputs = document.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(function (input) {
        input.addEventListener('input', function (e) {
            var val = e.target.value.replace(/\D/g, '');
            if (val.length >= 10) {
                val = '(' + val.substring(0, 3) + ') ' + val.substring(3, 6) + '-' + val.substring(6, 10);
            } else if (val.length >= 6) {
                val = '(' + val.substring(0, 3) + ') ' + val.substring(3, 6) + '-' + val.substring(6);
            } else if (val.length >= 3) {
                val = '(' + val.substring(0, 3) + ') ' + val.substring(3);
            }
            e.target.value = val;
        });
    });

    // ─── LAZY LOADING ───
    var lazyImages = document.querySelectorAll('img[loading="lazy"]');
    if ('loading' in HTMLImageElement.prototype) {
        // Browser supports native lazy loading
    } else {
        // Fallback with IntersectionObserver
        var imgObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    var img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    }
                    imgObserver.unobserve(img);
                }
            });
        });
        lazyImages.forEach(function (img) { imgObserver.observe(img); });
    }

    // ─── SMOOTH SCROLL ───
    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        anchor.addEventListener('click', function (e) {
            var target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // ─── FLEET STATS FETCH (for live counters) ───
    var statsSection = document.querySelector('.counters2');
    if (statsSection) {
        fetch('/api/fleet-stats')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                // Update counters if they exist
                var els = document.querySelectorAll('.counter');
                els.forEach(function (el) {
                    var currentCount = parseInt(el.getAttribute('data-count'));
                    if (currentCount === 0 && data.total) {
                        // Update with live data
                    }
                });
            })
            .catch(function () {
                // Silently fail — static data is already rendered
            });
    }

    // ─── BACK TO TOP ───
    var backToTop = document.createElement('button');
    backToTop.innerHTML = '<i class="bi bi-chevron-up"></i>';
    backToTop.className = 'asap-back-to-top';
    backToTop.style.cssText = 'position:fixed;bottom:30px;right:30px;width:46px;height:46px;border-radius:12px;background:#ff6b00;color:#fff;border:none;font-size:1.2rem;cursor:pointer;z-index:999;opacity:0;visibility:hidden;transition:all 0.3s;box-shadow:0 4px 16px rgba(255,107,0,0.3);';
    document.body.appendChild(backToTop);

    window.addEventListener('scroll', function () {
        if (window.pageYOffset > 400) {
            backToTop.style.opacity = '1';
            backToTop.style.visibility = 'visible';
        } else {
            backToTop.style.opacity = '0';
            backToTop.style.visibility = 'hidden';
        }
    }, { passive: true });

    backToTop.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

});
