const AdminChat = (function() {
    let client = null, channels = [], activeChannel = null, activeChannelId = null;
    let unreadTotal = 0, currentFilter = 'all';
    let pendingFile = null;
    let replyToMsg = null, ctxMenuMsg = null;
    
    // Media Recorder variables
    let mediaRecorder = null, audioChunks = [], recTimer = null, recSeconds = 0, recAnalyser = null, recAnimFrame = null;
    let longPressTimer = null, swipeStartX = 0, swipeTarget = null;
    
    let quickReplies = [];

    const EMOJIS = ['😊','😂','❤️','👍','🎉','🔥','👋','🙏','😍','🤝','💯','⭐','🚛','🚚','💰','✅','❌','📸','📎','⏰','🎯','💬','👏','🙌','😎','🤔','📞','📧'];
    const $ = id => document.getElementById(id);
    const esc = s => { const d = document.createElement('div'); d.textContent = s||''; return d.innerHTML; };
    
    // Custom Admin Notif Sound
    let notifSound = null;
    try { notifSound = new Audio('/assets/audio/notification.wav'); notifSound.preload = 'auto'; } catch(e) {}

    function fmtTime(d) {
        if (!d) return '';
        const dt = new Date(d), now = new Date();
        if (dt.toDateString() === now.toDateString()) return dt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
        return dt.toLocaleDateString([],{day:'numeric',month:'short'}) + ' ' + dt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
    }
    function getInitials(name) { return (name||'V').split(' ').map(w=>w[0]).join('').toUpperCase().substring(0,2); }
    
    // Fetch Quick Replies
    async function loadQuickReplies() {
        try {
            const res = await fetch('/api/admin/quick-replies');
            if(!res.ok) return;
            const data = await res.json();
            if(data.ok) {
                quickReplies = data.replies;
                renderQuickReplies();
            }
        } catch(e) {}
    }
    function renderQuickReplies() {
        const list = $('qrList');
        if(!quickReplies.length) {
            list.innerHTML = '<div style="padding:20px;text-align:center;color:#999;font-size:0.9rem">Aucune réponse rapide. Ajoutez-en une !</div>';
            return;
        }
        list.innerHTML = quickReplies.map(qr => {
            const safeText = qr.text.replace(/'/g, "\\'").replace(/"/g, "&quot;");
            return `<div class="qr-list-item">
                <div class="qr-text" onclick="AdminChat.useQuickReply('${safeText}')">${esc(qr.text)}</div>
                <button class="qr-delete" onclick="AdminChat.deleteQuickReply('${qr.id}')"><i class="bi bi-trash"></i></button>
            </div>`;
        }).join('');
    }

    function renderList() {
        const search = ($('convSearch').value||'').toLowerCase();
        let filtered = channels;
        if(search) filtered = filtered.filter(ch => {
            const n = (ch.data.visitor_name||'').toLowerCase(), e = (ch.data.visitor_email||'').toLowerCase();
            return n.includes(search) || e.includes(search);
        });
        if(currentFilter === 'unread') filtered = filtered.filter(ch => ch.countUnread() > 0);
        
        unreadTotal = 0;
        channels.forEach(ch => unreadTotal += ch.countUnread());
        
        const badge = $('sidebarBadge');
        const urlBadge = $('unreadBadgeTotal');
        if(unreadTotal > 0) {
            if(badge) { badge.textContent = unreadTotal; badge.style.display='inline'; }
            if(urlBadge) { urlBadge.textContent = unreadTotal; urlBadge.style.display='inline-block'; }
            document.title = `(${unreadTotal}) Chat ASAP`;
        } else {
            if(badge) badge.style.display='none';
            if(urlBadge) urlBadge.style.display='none';
            document.title = 'Chat — ASAP Admin';
        }

        if(!filtered.length) {
            $('convList').innerHTML = '<div class="chat-empty-state" style="padding:40px;"><i class="bi bi-inbox" style="font-size:3rem; margin-bottom:10px;"></i><p style="font-size:0.9rem">Aucune conversation</p></div>';
            return;
        }

        $('convList').innerHTML = filtered.map(ch => {
            const d = ch.data, name = d.visitor_name || 'Visiteur';
            const lm = ch.state.messages.length ? ch.state.messages[ch.state.messages.length - 1] : null;
            const lt = lm ? (lm.text || (lm.attachments && lm.attachments.length ? (lm.attachments[0].type==='image'?'📷 Photo':lm.attachments[0].type==='audio'?'🎤 Message vocal':'📎 Fichier') : '')) : 'Nouvelle conversation';
            const t = lm ? fmtTime(lm.created_at) : fmtTime(ch.data.created_at);
            const u = ch.countUnread();
            const isOnline = ch.state.watchers && Object.keys(ch.state.watchers).length > 1; 
            
            return `<div class="conv-item ${ch.id === activeChannelId ? 'active' : ''}" onclick="AdminChat.selectConv('${ch.id}')">
                <div class="conv-avatar-wrapper">
                    <div class="conv-avatar">${getInitials(name)}</div>
                    ${isOnline ? '<div class="online-dot"></div>' : ''}
                </div>
                <div class="conv-info">
                    <div class="conv-row-top">
                        <div class="conv-name">${esc(name)}</div>
                        <div class="conv-time">${t}</div>
                    </div>
                    <div class="conv-row-bottom">
                        <div class="conv-last-msg">${esc(lt)}</div>
                        ${u > 0 ? `<div class="conv-unread">${u}</div>` : ''}
                    </div>
                </div>
            </div>`;
        }).join('');
    }

    function renderMsgs() {
        if(!activeChannel) return;
        const el = $('chatMessages');
        el.innerHTML = '';
        
        let lastDate = null;
        let lastAuthor = null;
        const msgs = activeChannel.state.messages;

        for(let i=0; i<msgs.length; i++) {
            const msg = msgs[i];
            if(msg._localDeleted) continue; // skip locally deleted

            const isA = msg.user && msg.user.id === 'asap-admin';
            const div = document.createElement('div');
            div.className = 'chat-msg ' + (isA ? 'admin' : 'visitor');
            div.dataset.msgId = msg.id;
            
            // Grouping Logic
            const prevMsg = i > 0 ? msgs[i-1] : null;
            const nextMsg = i < msgs.length - 1 ? msgs[i+1] : null;
            const samePrev = prevMsg && prevMsg.user && prevMsg.user.id === (msg.user?msg.user.id:'') && (new Date(msg.created_at) - new Date(prevMsg.created_at) < 5*60000);
            const sameNext = nextMsg && nextMsg.user && nextMsg.user.id === (msg.user?msg.user.id:'') && (new Date(nextMsg.created_at) - new Date(msg.created_at) < 5*60000);
            
            if(!samePrev) div.classList.add('group-first');
            if(!sameNext) div.classList.add('group-last');

            let content = '';

            // Deleted Message check
            if(msg.deleted_at || msg.type === 'deleted') {
                div.innerHTML = `<div class="bubble deleted"><span>🚫 Message supprimé</span></div>`;
                el.appendChild(div);
                continue;
            }

            // Quoted message
            if (msg.quoted_message) {
                const q = msg.quoted_message;
                const qAuthor = q.user ? (q.user.id === 'asap-admin' ? 'Vous' : q.user.name || 'Visiteur') : '';
                let qText = q.text || '';
                if (!qText && q.attachments && q.attachments.length) {
                    const a = q.attachments[0];
                    qText = a.type === 'image' ? '📷 Photo' : a.type === 'audio' ? '🎤 Voice message' : '📎 ' + (a.name || 'File');
                }
                if (qText.length > 60) qText = qText.substring(0, 60) + '…';
                content += `<div class="quote-block" onclick="AdminChat.scrollToMsg('${q.id}')"><div class="qb-author">${esc(qAuthor)}</div><div class="qb-text">${esc(qText)}</div></div>`;
            }

            if(!isA && !samePrev) content += `<div class="sender-name">${esc(msg.user?msg.user.name:'Visiteur')}</div>`;
            if(msg.text) content += `<span>${esc(msg.text).replace(/\n/g, '<br>')}</span>`;
            
            // Attachments
            if(msg.attachments && msg.attachments.length) {
                msg.attachments.forEach(att => {
                    if(att.type === 'image') {
                        const src = att.image_url || att.thumb_url || att.asset_url;
                        content += `<img src="${src}" alt="" onclick="AdminChat.openLightbox('${src}')">`;
                    } else if(att.type === 'audio') {
                        const dur = att.duration || 0;
                        const m = Math.floor(dur/60), s = dur%60;
                        const durStr = m + ':' + (s<10?'0':'') + s;
                        const waveBars = Array.from({length:30}, () => `<span style="height:${Math.max(3,Math.random()*24)}px"></span>`).join('');
                        content += `<div class="audio-player" data-src="${att.asset_url}" data-dur="${dur}">
                            <button class="play-btn" onclick="AdminChat.playAudio(this)"><i class="bi bi-play-fill"></i></button>
                            <div class="audio-wave" onclick="AdminChat.seekAudio(event,this)">${waveBars}</div>
                            <span class="audio-dur">${durStr}</span>
                        </div>`;
                    } else {
                        const name = att.title || att.name || 'Fichier';
                        const ext = name.split('.').pop().toLowerCase();
                        let icon = 'bi-file-earmark';
                        if (ext === 'pdf') icon = 'bi-file-pdf text-danger';
                        content += `<a class="file-attach" href="${att.asset_url||'#'}" target="_blank"><i class="bi ${icon}"></i> ${esc(name)}</a>`;
                    }
                });
            }

            // Ticks (Read receipt) if it's admin
            let ticks = '';
            if(isA) {
                const isRead = activeChannel.state.read && Object.keys(activeChannel.state.read).some(uid => uid !== 'asap-admin' && activeChannel.state.read[uid].last_read >= new Date(msg.created_at));
                ticks = isRead ? '<span class="ticks read">✓✓</span>' : '<span class="ticks">✓</span>';
            }

            const hoverActions = `<div class="msg-hover-actions">
                <button onclick="AdminChat.setReply('${msg.id}')" title="Répondre"><i class="bi bi-reply-fill"></i></button>
                ${isA ? '' : `<button onclick="AdminChat.showReactionBar(event, '${msg.id}')" title="Réagir"><i class="bi bi-emoji-smile"></i></button>`}
                <button onclick="AdminChat.showCtxMenu(event, '${msg.id}', ${isA})" title="Options"><i class="bi bi-chevron-down"></i></button>
            </div>`;

            div.innerHTML = `${hoverActions}<div class="bubble">${content}</div><div class="msg-reactions" id="rx-${msg.id}"></div><div class="meta">${fmtTime(msg.created_at)} ${ticks}</div>`;

            // Mobile Swipe & Long press
            div.addEventListener('touchstart', function(e) {
                if(!window.matchMedia("(max-width: 767px)").matches) return;
                longPressTimer = setTimeout(() => {
                    if(navigator.vibrate) navigator.vibrate(50);
                    AdminChat.showCtxMenu(e, msg.id, isA);
                }, 500);
                swipeStartX = e.touches[0].clientX;
                swipeTarget = div;
            }, {passive:true});
            div.addEventListener('touchmove', function(e) {
                clearTimeout(longPressTimer);
                const dx = e.touches[0].clientX - swipeStartX;
                if(dx > 20 && swipeTarget === div) { div.style.transform = `translateX(${Math.min(dx, 60)}px)`; div.style.transition = 'none'; }
            }, {passive:true});
            div.addEventListener('touchend', function(e) {
                clearTimeout(longPressTimer);
                if(swipeTarget === div) {
                    const dx = parseInt(div.style.transform.replace(/[^0-9-]/g,'')) || 0;
                    if(dx > 50) { if(navigator.vibrate) navigator.vibrate(30); AdminChat.setReply(msg.id); }
                    div.style.transform = ''; div.style.transition = 'transform .2s ease'; swipeTarget = null;
                }
            }, {passive: true});

            // Reactions
            if(msg.reaction_counts) {
                setTimeout(() => renderReactions(msg.id, msg.reaction_counts, msg.own_reactions || []), 0);
            }

            el.appendChild(div);
        }
        // Auto scroll down
        el.scrollTop = el.scrollHeight;
        $('scrollBadge').style.display = 'none';
    }

    function renderReactions(msgId, counts, ownReactions) {
        const container = document.getElementById('rx-' + msgId);
        if (!container) return;
        container.innerHTML = '';
        const ownTypes = (ownReactions || []).map(r => r.type);
        Object.entries(counts || {}).forEach(([type, count]) => {
            if (count <= 0) return;
            const isMine = ownTypes.includes(type);
            const pill = document.createElement('span');
            pill.className = 'rx-pill' + (isMine ? ' mine' : '');
            pill.innerHTML = `<span class="rx-emoji">${type}</span><span class="rx-count">${count}</span>`;
            pill.onclick = () => AdminChat.toggleReaction(msgId, type);
            container.appendChild(pill);
        });
    }

    function populateVisitorInfo() {
        if(!activeChannel) return;
        const d = activeChannel.data;
        const msgs = activeChannel.state.messages;
        let images = [], files = [];
        msgs.forEach(m => {
            if(!m.deleted_at && m.attachments) {
                m.attachments.forEach(a => {
                    if(a.type==='image') images.push(a);
                    else files.push(a);
                });
            }
        });
        $('vipContent').innerHTML = `
            <div class="vip-avatar">${getInitials(d.visitor_name)}</div>
            <div class="vip-name">${esc(d.visitor_name)}</div>
            <div style="color:var(--text-muted);font-size:0.9rem;margin-bottom:20px">${esc(d.visitor_email)}</div>
            
            <div class="vip-item">
                <h6>Page de contact</h6>
                <p><i class="bi bi-geo-alt" style="color:var(--primary)"></i> <a href="${esc(d.visitor_page)}" target="_blank" style="color:var(--text-main)">${esc(d.visitor_page)}</a></p>
            </div>
            
            <div class="vip-item">
                <h6>Statistiques</h6>
                <p><i class="bi bi-chat-left-text" style="color:var(--primary); margin-right:5px;"></i> ${msgs.length} messages échangés</p>
                <p style="font-size:0.8rem;color:#999;margin-top:4px">Créé le ${new Date(d.created_at).toLocaleDateString()}</p>
            </div>
            
            ${images.length ? `<div class="vip-item">
                <h6>Photos & Médias (${images.length})</h6>
                <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:8px">
                    ${images.map(img => `<img src="${img.thumb_url||img.image_url||img.asset_url}" style="width:60px;height:60px;object-fit:cover;border-radius:4px;cursor:pointer" onclick="AdminChat.openLightbox('${img.image_url||img.asset_url}')">`).join('')}
                </div>
            </div>` : ''}
        `;
    }
    
    async function compressImage(file) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = function() {
                let w = img.width, h = img.height; const MAX = 1200;
                if(w > MAX || h > MAX) { if(w > h){h=Math.round(h*MAX/w);w=MAX;}else{w=Math.round(w*MAX/h);h=MAX;} }
                const canvas = document.createElement('canvas');
                canvas.width=w; canvas.height=h;
                canvas.getContext('2d').drawImage(img,0,0,w,h);
                canvas.toBlob(blob => blob ? resolve(new File([blob], file.name, {type:'image/jpeg'})) : reject('Err'), 'image/jpeg', 0.8);
            };
            img.onerror=reject; img.src=URL.createObjectURL(file);
        });
    }

    return {
        init: async function() {
            try {
                const res = await fetch('/api/chat/admin-token');
                if(!res.ok) throw new Error('Token error');
                const authData = await res.json();
                
                client = new StreamChat(authData.api_key);
                await client.connectUser({id: authData.user_id, name: 'Support ASAP'}, authData.token);
                
                const filter = { type: 'messaging', members: { $in: ['asap-admin'] } };
                const sort = [{ field: 'last_message_at', direction: -1 }];
                channels = await client.queryChannels(filter, sort, { watch:true, state:true, limit:50 });
                
                // Events
                client.on('message.new', event => {
                    renderList();
                    if(activeChannel && event.cid === activeChannel.cid) {
                        renderMsgs();
                        try { activeChannel.markRead(); } catch(e){}
                    } else {
                        if(notifSound && event.user.id !== 'asap-admin') notifSound.play();
                    }
                });
                
                client.on('typing.start', event => {
                    if(activeChannel && event.cid === activeChannel.cid && event.user.id !== 'asap-admin') {
                        $('chatTyping').style.display = 'block';
                        $('scrollBadge').style.display = 'none';
                    }
                });
                
                client.on('typing.stop', event => {
                    if(activeChannel && event.cid === activeChannel.cid && event.user.id !== 'asap-admin') {
                        $('chatTyping').style.display = 'none';
                    }
                });

                client.on('message.updated', event => { if(activeChannel && event.cid === activeChannel.cid) renderMsgs(); });
                client.on('message.deleted', event => { if(activeChannel && event.cid === activeChannel.cid) renderMsgs(); });
                client.on('reaction.new', event => { if(activeChannel && event.cid === activeChannel.cid) renderMsgs(); });
                client.on('reaction.deleted', event => { if(activeChannel && event.cid === activeChannel.cid) renderMsgs(); });

                renderList();
                loadQuickReplies();
                
                $('convSearch').addEventListener('input', () => renderList());
                
            } catch(e) { console.error('Init fail', e); }
        },
        
        setFilter: function(f) {
            currentFilter = f;
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            document.querySelector(`.filter-btn[data-filter="${f}"]`).classList.add('active');
            renderList();
        },

        selectConv: async function(cid) {
            const ch = channels.find(c => c.id === cid);
            if(!ch) return;
            activeChannel = ch;
            activeChannelId = cid;
            
            // UI changes
            renderList();
            $('noConvSelected').style.display = 'none';
            $('activeConvArea').style.display = 'flex';
            
            // Header details
            $('activeName').textContent = ch.data.visitor_name || 'Visiteur';
            $('activeAvatar').innerHTML = getInitials(ch.data.visitor_name);
            const isOnline = ch.state.watchers && Object.keys(ch.state.watchers).length > 1;
            $('activeStatus').textContent = isOnline ? 'En ligne' : 'Hors ligne';
            
            renderMsgs();
            populateVisitorInfo();
            
            try { await activeChannel.markRead(); } catch(e){}
            
            if(window.matchMedia("(max-width: 767px)").matches) {
                $('chatWindow').classList.add('active');
            }
        },
        closeConv: function(e) {
            if(e) { e.preventDefault(); e.stopPropagation(); }
            $('chatWindow').classList.remove('active');
            setTimeout(() => {
                activeChannel = null; activeChannelId = null;
                $('noConvSelected').style.display = 'flex';
                $('activeConvArea').style.display = 'none';
                renderList();
            }, 300);
        },
        
        // Sending
        send: async function() {
            const input = $('chatInput');
            const text = input.value.trim();
            if(!text && !pendingFile) return;
            if(!activeChannel) return;

            $('chatSendBtn').disabled = true;

            try {
                let attachments = [];
                if(pendingFile) {
                    const isImage = pendingFile.type.startsWith('image/');
                    let fUpload = pendingFile;
                    if(isImage && pendingFile.size > 2*1024*1024) try { fUpload = await compressImage(pendingFile); }catch(e){}
                    const resp = await activeChannel.sendFile(fUpload);
                    attachments.push({
                        type: isImage?'image':'file',
                        [isImage?'image_url':'asset_url']: resp.file,
                        title: pendingFile.name, name: pendingFile.name
                    });
                    this.clearFile();
                }
                
                const msgPayload = { text: text || undefined, attachments };
                if(replyToMsg) msgPayload.quoted_message_id = replyToMsg.id;
                
                await activeChannel.sendMessage(msgPayload);
                this.cancelReply();
                input.value = ''; input.style.height = 'auto'; this.checkInputStatus();
            } catch(e) { console.error('Send failed', e); }
            $('chatSendBtn').disabled = false;
        },
        
        onKeyDown: function(e) {
            if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send(); }
            if(activeChannel && e.key !== 'Enter') { try{ activeChannel.keystroke(); }catch(e){} }
            setTimeout(() => this.checkInputStatus(), 10);
        },
        autoResize: function(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight, 120)+'px'; this.checkInputStatus(); },
        checkInputStatus: function() {
            const v = $('chatInput').value.trim();
            const btn = $('chatSendBtn');
            btn.disabled = (!v && !pendingFile);
            if(v || pendingFile) $('inputArea').classList.add('has-text'); else $('inputArea').classList.remove('has-text');
        },
        
        setReply: function(id) {
            if(!activeChannel) return;
            const m = activeChannel.state.messages.find(msg => msg.id === id);
            if(!m) return;
            replyToMsg = m;
            const author = m.user.id==='asap-admin' ? 'Vous' : m.user.name||'Visiteur';
            let txt = m.text||'';
            if(!txt && m.attachments&&m.attachments.length) txt = m.attachments[0].type==='image'?'📷 Photo':m.attachments[0].type==='audio'?'🎤 Message vocal':'📎 Document';
            if(txt.length > 50) txt = txt.substring(0,50)+'...';
            $('replyName').textContent = 'Réponse à ' + author;
            $('replyText').textContent = txt;
            $('replyPreview').classList.add('show');
            $('chatInput').focus();
        },
        cancelReply: function() { replyToMsg = null; $('replyPreview').classList.remove('show'); },
        
        onFileSelect: function(e) {
            const f = e.target.files[0]; if(!f) return;
            if(f.size > 20*1024*1024) return alert('20MB max');
            pendingFile = f;
            $('chatFileName').textContent = f.name;
            $('chatFilePreview').classList.add('show');
            this.checkInputStatus();
        },
        clearFile: function() { pendingFile = null; $('chatFileInput').value = ''; $('chatFilePreview').classList.remove('show'); this.checkInputStatus(); },
        
        // Audio Recording
        toggleRecording: async function() {
            if(mediaRecorder) return this.cancelRecording();
            try {
                const stream = await navigator.mediaDevices.getUserMedia({audio:true});
                mediaRecorder = new MediaRecorder(stream, {mimeType: 'audio/webm'});
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                recAnalyser = audioCtx.createAnalyser();
                const source = audioCtx.createMediaStreamSource(stream);
                source.connect(recAnalyser);
                recAnalyser.fftSize = 64;
                const bLength = recAnalyser.frequencyBinCount;
                const dataArray = new Uint8Array(bLength);
                
                audioChunks = []; recSeconds = 0;
                mediaRecorder.ondataavailable = e => { if(e.data.size > 0) audioChunks.push(e.data); };
                
                const draw = () => {
                    if(!mediaRecorder) return;
                    recAnimFrame = requestAnimationFrame(draw);
                    recAnalyser.getByteFrequencyData(dataArray);
                    const canvas = $('recCanvas'), ctx = canvas.getContext('2d');
                    ctx.clearRect(0,0, canvas.width, canvas.height);
                    ctx.fillStyle = '#cf000e';
                    for(let i=0; i<30; i++) {
                        const v = Math.max(3, dataArray[i]/2 - 10);
                        ctx.fillRect(i*3 + 5, canvas.height/2 - v/2, 2, v);
                    }
                };
                
                mediaRecorder.start(200);
                $('recordingUI').style.display = 'flex';
                $('recTime').textContent = '0:00';
                recTimer = setInterval(() => {
                    recSeconds++;
                    const m = Math.floor(recSeconds/60), s = recSeconds%60;
                    $('recTime').textContent = m + ':' + (s<10?'0':'') + s;
                }, 1000);
                draw();
            } catch(e) { alert('Microphone invalide ou non autorisé.'); }
        },
        cancelRecording: function() {
            if(mediaRecorder) { mediaRecorder.stream.getTracks().forEach(t => t.stop()); mediaRecorder = null; }
            if(recTimer) clearInterval(recTimer);
            if(recAnimFrame) cancelAnimationFrame(recAnimFrame);
            $('recordingUI').style.display = 'none';
        },
        stopAndSendRecording: async function() {
            if(!mediaRecorder || !activeChannel) return;
            $('recordingUI').style.display = 'none';
            $('chatSendBtn').disabled = true;
            
            mediaRecorder.onstop = async () => {
                mediaRecorder.stream.getTracks().forEach(t => t.stop());
                if(audioChunks.length === 0) return;
                const blob = new Blob(audioChunks, {type: 'audio/webm'});
                const file = new File([blob], 'voice-'+Date.now()+'.webm', {type: blob.type});
                try {
                    const resp = await activeChannel.sendFile(file);
                    await activeChannel.sendMessage({attachments: [{
                        type: 'audio', asset_url: resp.file,
                        title: 'Voice', name: file.name,
                        mime_type: blob.type, file_size: blob.size,
                        duration: recSeconds
                    }]});
                } catch(e) {}
                $('chatSendBtn').disabled = false;
                mediaRecorder = null;
            };
            mediaRecorder.stop();
            if(recTimer) clearInterval(recTimer);
            if(recAnimFrame) cancelAnimationFrame(recAnimFrame);
        },
        
        // Audio Playback
        playAudio: function(btn) {
            const p = btn.closest('.audio-player');
            let a = document.getElementById('chatAudio');
            if(!a) { a = document.createElement('audio'); a.id = 'chatAudio'; document.body.appendChild(a); }
            
            if(a.src !== p.dataset.src) {
                document.querySelectorAll('.audio-player .play-btn i').forEach(i => i.className='bi bi-play-fill');
                a.src = p.dataset.src;
                const sp = parseFloat(p.querySelector('.speed-btn')?.dataset?.v || 1);
                a.playbackRate = sp;
                a.play();
                btn.innerHTML = '<i class="bi bi-pause-fill"></i>';
                a.ontimeupdate = () => {
                    const pct = a.currentTime / a.duration;
                    const w = p.querySelector('.audio-wave');
                    Array.from(w.children).forEach((span, idx) => { span.style.opacity = (idx/30) <= pct ? '1' : '0.4'; });
                };
                a.onended = () => { btn.innerHTML = '<i class="bi bi-play-fill"></i>'; };
            } else {
                if(a.paused) { a.play(); btn.innerHTML = '<i class="bi bi-pause-fill"></i>'; }
                else { a.pause(); btn.innerHTML = '<i class="bi bi-play-fill"></i>'; }
            }
        },
        seekAudio: function(e, wrap) {
            const a = document.getElementById('chatAudio');
            if(a && a.src === wrap.closest('.audio-player').dataset.src) {
                const rect = wrap.getBoundingClientRect();
                a.currentTime = a.duration * ((e.clientX - rect.left) / rect.width);
            }
        },
        
        // Quick Replies
        toggleQRPanel: function() {
            const p = $('qrPanel');
            p.style.display = p.style.display==='flex' ? 'none' : 'flex';
        },
        addQuickReply: async function() {
            const v = $('newQRInput').value.trim();
            if(!v) return;
            try {
                const res = await fetch('/api/admin/quick-replies', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({text: v}) });
                if(res.ok) { $('newQRInput').value=''; loadQuickReplies(); }
            } catch(e){}
        },
        deleteQuickReply: async function(id) {
            try {
                await fetch('/api/admin/quick-replies/' + id, { method: 'DELETE' });
                loadQuickReplies();
            } catch(e){}
        },
        useQuickReply: function(text) {
            const i = $('chatInput');
            i.value += (i.value?' ':'') + text;
            this.toggleQRPanel(); this.autoResize(i); i.focus();
        },
        
        // UI Helpers
        scrollToBottom: function() { $('chatMessages').scrollTop = $('chatMessages').scrollHeight; $('scrollBadge').style.display='none'; },
        onScroll: function() {
            const el = $('chatMessages');
            if(el.scrollHeight - el.scrollTop > el.clientHeight + 100) $('scrollBadge').style.display = 'block';
            else $('scrollBadge').style.display = 'none';
        },
        scrollToMsg: function(id) {
            const el = document.querySelector(`.chat-msg[data-msg-id="${id}"]`);
            if(el) {
                el.scrollIntoView({behavior:'smooth', block:'center'});
                el.classList.add('highlight');
                setTimeout(() => el.classList.remove('highlight'), 1600);
            }
        },
        
        // Lightbox
        openLightbox: function(src) { $('lightboxImg').src = src; $('lightboxDl').href = src; $('chatLightbox').style.display='flex'; },
        closeLightbox: function() { $('chatLightbox').style.display='none'; },
        
        // Context Menu & Reactions
        toggleReaction: async function(msgId, rxType) {
            try {
                const m = activeChannel.state.messages.find(x => x.id === msgId);
                if(m && m.own_reactions && m.own_reactions.some(r => r.type===rxType)) await activeChannel.deleteReaction(msgId, rxType);
                else await activeChannel.sendReaction(msgId, {type: rxType});
            }catch(e){}
            const rb = document.querySelector('.reactions-bar'); if(rb) rb.remove();
        },
        showReactionBar: function(e, msgId) {
            e.preventDefault(); e.stopPropagation();
            document.querySelectorAll('.reactions-bar').forEach(b=>b.remove());
            const b = document.createElement('div'); b.className = 'reactions-bar show';
            b.innerHTML = ['👍','❤️','😂','😮','😢','🙏'].map(r => `<span onclick="AdminChat.toggleReaction('${msgId}','${r}')">${r}</span>`).join('');
            document.body.appendChild(b);
            const rect = e.target.getBoundingClientRect();
            b.style.top = (rect.top - 45) + 'px'; b.style.left = Math.max(10, rect.left - 50) + 'px';
            const closeRx = ev => { if(!b.contains(ev.target)) { b.remove(); document.removeEventListener('click', closeRx); } };
            setTimeout(() => document.addEventListener('click', closeRx), 10);
        },
        showCtxMenu: function(e, msgId, isAdminMsg) {
            e.preventDefault(); e.stopPropagation();
            document.querySelectorAll('.ctx-menu').forEach(m => m.remove());
            const menu = document.createElement('div'); menu.className = 'ctx-menu show';
            menu.innerHTML = `
                <div class="ctx-item" onclick="AdminChat.setReply('${msgId}')"><i class="bi bi-reply"></i> Répondre</div>
                <div class="ctx-item" onclick="AdminChat.copyMsg('${msgId}')"><i class="bi bi-files"></i> Copier</div>
                <div class="ctx-item danger" onclick="AdminChat.deleteMsg('${msgId}')"><i class="bi bi-trash"></i> Supprimer</div>
            `;
            document.body.appendChild(menu);
            const rect = e.target.getBoundingClientRect();
            const menuX = Math.min(rect.left, window.innerWidth - 180);
            const menuY = Math.min(rect.bottom + 5, window.innerHeight - 150);
            menu.style.left = menuX + 'px'; menu.style.top = menuY + 'px';
            
            const closeMenu = ev => { if(!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('click', closeMenu); } };
            setTimeout(() => document.addEventListener('click', closeMenu), 10);
        },
        copyMsg: function(id) {
            const m = activeChannel.state.messages.find(x => x.id === id);
            if(m && m.text) { navigator.clipboard.writeText(m.text); }
            document.querySelectorAll('.ctx-menu').forEach(m => m.remove());
        },
        deleteMsg: async function(id) {
            if(!confirm("Supprimer ce message pour vous et le visiteur ?")) return;
            try {
                await client.deleteMessage(id, false);
                const msgDiv = document.querySelector(`.chat-msg[data-msg-id="${id}"]`);
                if(msgDiv) {
                    const mObj = activeChannel.state.messages.find(x => x.id === id);
                    if(mObj) mObj._localDeleted = true;
                    renderMsgs();
                }
            }catch(e){ alert('Impossible de supprimer ce message (trop ancien ou droits insuffisants).'); }
            document.querySelectorAll('.ctx-menu').forEach(m => m.remove());
        },
        
        // Global Options Menus
        showGlobalMenu: function(e) {
            e.preventDefault(); e.stopPropagation();
            document.querySelectorAll('.ctx-menu').forEach(m => m.remove());
            const menu = document.createElement('div'); menu.className = 'ctx-menu show';
            menu.innerHTML = `
                <div class="ctx-item" onclick="AdminChat.toggleGlobalNotifications()"><i class="bi bi-bell-slash"></i> Couper Notifications</div>
                <div class="ctx-item danger" onclick="AdminChat.deleteAllHistory()"><i class="bi bi-trash"></i> Tout purger</div>
            `;
            document.body.appendChild(menu);
            const rect = e.target.getBoundingClientRect();
            menu.style.right = (window.innerWidth - rect.right) + 'px'; menu.style.top = (rect.bottom + 5) + 'px';
            
            const closeMenu = ev => { if(!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('click', closeMenu); } };
            setTimeout(() => document.addEventListener('click', closeMenu), 10);
        },
        toggleGlobalNotifications: function() {
            if(notifSound) {
                notifSound = null;
                alert("Notifications sonores désactivées pour cette session.");
            } else {
                try { notifSound = new Audio('/assets/audio/notification.wav'); notifSound.preload='auto'; alert("Son activé."); }catch(e){}
            }
        },
        deleteAllHistory: function() {
            alert('Purger tout requiert les droits Super Admin côté serveur.');
        },

        showConvSearch: function(e) {
            alert('Fonction Recherche : Tapez CTRL+F dans la conversation.');
        },

        showConvMenu: function(e) {
            if(!activeChannel) return;
            e.preventDefault(); e.stopPropagation();
            document.querySelectorAll('.ctx-menu').forEach(m => m.remove());
            const menu = document.createElement('div'); menu.className = 'ctx-menu show';
            menu.innerHTML = `
                <div class="ctx-item" onclick="AdminChat.toggleVisitorInfo()"><i class="bi bi-info-circle"></i> Infos contact</div>
                <div class="ctx-item danger" onclick="AdminChat.deleteConv()"><i class="bi bi-trash"></i> Supprimer le chat</div>
            `;
            document.body.appendChild(menu);
            const rect = e.target.getBoundingClientRect();
            menu.style.right = (window.innerWidth - rect.right) + 'px'; menu.style.top = (rect.bottom + 5) + 'px';
            
            const closeMenu = ev => { if(!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('click', closeMenu); } };
            setTimeout(() => document.addEventListener('click', closeMenu), 10);
        },

        deleteConv: async function() {
            if(!activeChannel || !confirm('Supprimer définitivement cette conversation ?')) return;
            try {
                await activeChannel.delete();
                this.closeConv();
                channels = channels.filter(c => c.id !== activeChannel.id);
                renderList();
            } catch(e) { alert('Erreur suppression chat.'); }
        },

        toggleVisitorInfo: function() {
            const p = $('visitorInfoPanel');
            p.classList.toggle('open');
        },

        // Web Push Auto-subscribe
        setupWebPush: async function() {
            try {
                // Fetch public key
                const req = await fetch('/api/push/vapid-key');
                if(!req.ok) return;
                const vapidData = await req.json();
                if(!vapidData || !vapidData.publicKey) return;

                const reg = await navigator.serviceWorker.ready;
                const key = vapidData.publicKey;
                const padding = '='.repeat((4 - key.length % 4) % 4);
                const base64 = (key + padding).replace(/-/g, '+').replace(/_/g, '/');
                const rawData = atob(base64);
                const authKey = new Uint8Array(rawData.length);
                for (let i = 0; i < rawData.length; i++) authKey[i] = rawData.charCodeAt(i);

                let oldSub = await reg.pushManager.getSubscription();
                let needsSubscribe = true;

                if (oldSub) {
                    try {
                        const curKeyArray = new Uint8Array(oldSub.options.applicationServerKey);
                        let match = curKeyArray.length === authKey.length;
                        if (match) {
                            for(let i=0; i<curKeyArray.length; ++i) { if(curKeyArray[i] !== authKey[i]) { match=false; break; } }
                        }
                        if (!match) await oldSub.unsubscribe();
                        else needsSubscribe = false;
                    } catch(e) { await oldSub.unsubscribe(); }
                }

                let sub = oldSub;
                if (needsSubscribe) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: authKey });
                if(sub) await fetch('/api/push/subscribe', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ subscription: sub.toJSON() }) });
            } catch(e) {}
        }
    };
})();

document.addEventListener('DOMContentLoaded', () => {
    AdminChat.init();
    if ('serviceWorker' in navigator && 'PushManager' in window) {
        Notification.requestPermission().then(p => { if(p === 'granted') AdminChat.setupWebPush(); });
    }
});

// Fix iOS viewport heights natively
function setVH(){
    document.documentElement.style.setProperty('--vh', (window.innerHeight * 0.01) + 'px');
    const m = document.querySelector('.admin-main'); if(m) m.style.height = window.innerHeight + 'px';
}
setVH(); window.addEventListener('resize', setVH);
if(window.visualViewport) window.visualViewport.addEventListener('resize', () => {
    const m = document.querySelector('.admin-main'); if(m) m.style.height = window.visualViewport.height + 'px';
});
