"""Embedded JavaScript that runs inside WhatsApp's WebView2 page.

parley speaks to the exact page WhatsApp Desktop renders. That page is the
WhatsApp Web client, so it exposes:

1. a webpack bundle with a live module cache (``webpackChunkwhatsapp_web_client``)
   holding the message/chat/contact "Store" modules, and
2. the rendered DOM.

Discovery uses the standard *module raid*: we push a unique, empty chunk into
the webpack registry, whose loader answers with the module cache ``e`` without
executing any application code. From that cache we locate the Store-shaped
module (``Chat.getModelsArray`` + ``Msg.getModelsArray``) and keep a pointer so
every later call resolves it in one hop. Reading never executes app modules.

Every snippet is defensive: return nulls / [] instead of throwing, never run
untrusted module bodies, and degrade to the DOM when unobtainable.
"""

# Registry names we know WhatsApp builds use. New builds rename at most the
# suffix, so we scan all of them.
CHUNK_REGS = [
    "webpackChunkwhatsapp_web_client",
    "webpackChunkwhatsapp_web",
    "webpackChunkwhatsapp_desktop",
    "webpackChunkWA",
]



RESOLVE_S_JS = r"""
(regNames) => {
  if (window.__parleyResolve) return { available: true, via: "cached" };
  try {
    // 1) preferred: WhatsApp's own require loader exposes the Store as
    //    WAWebCollections (current WinUI3 desktop + modern web builds).
    const R = window.require;
    if (typeof R === "function") {
      for (const storeId of ["WAWebCollections", "Store"]) {
        let v = null;
        try { v = R(storeId); } catch (e) {}
        if (v && typeof v === "object"
            && v.Chat && typeof v.Chat.getModelsArray === "function"
            && v.Msg && typeof v.Msg.getModelsArray === "function") {
          window.__parleyCache = v;
          window.__parleyResolve = () => window.__parleyCache;
          window.__parleyStore = { via: storeId, moduleId: null };
          return { available: true, via: "require:" + storeId };
        }
      }
    }
    // 2) module raid on a webpack chunk registry (older browser builds)
    const regs = (Array.isArray(regNames) && regNames.length)
      ? regNames
      : Object.keys(window).filter((k) => k.startsWith("webpackChunk"));
    for (const regName of regs) {
      const reg = window[regName];
      if (!reg || typeof reg.push !== "function") continue;
      if (String(reg.push).indexOf("native") >= 0) continue; // no webpack loader
      let cache = null;
      try {
        let got = false;
        window.__parleyHook = (e) => { cache = e; got = true; };
        reg.push([["__parley_probe__"], {}, window.__parleyHook]);
        if (!got && cache === null) continue;
      } catch (e) { continue; }
      if (!cache || typeof cache !== "object") continue;
      for (const id of Object.keys(cache)) {
        const m = cache[id];
        const v = m && (m.default || m);
        if (v && typeof v === "object"
            && v.Chat && typeof v.Chat.getModelsArray === "function"
            && v.Msg && typeof v.Msg.getModelsArray === "function") {
          window.__parleyCache = cache;
          window.__parleyResolve = (ptr) => {
            const host = window.__parleyCache;
            if (!host) return null;
            const mod = host[ptr.moduleId];
            return (mod && (mod.default || mod)) || null;
          };
          window.__parleyStore = { via: "raid", moduleId: id };
          return { available: true, via: "raid" };
        }
      }
    }
    // 3) legacy direct window.Store
    if (window.Store && window.Store.Chat && typeof window.Store.Chat.getModelsArray === "function") {
      window.__parleyResolve = () => window.Store;
      window.__parleyStore = null;
      return { available: true, via: "direct" };
    }
    return { available: false, reason: "no Store module (require/WAWebCollections, raid, direct all missed)" };
  } catch (e) {
    return { available: false, reason: String(e) };
  }
}
"""

STATUS_JS = r"""
() => {
  try {
    const S = window.__parleyResolve ? window.__parleyResolve(window.__parleyStore) : (window.Store || null);
    let me = null;
    let connected = null;
    try {
      if (S && S.Conn && (S.Conn.connected !== undefined)) connected = !!S.Conn.connected;
      if (S && S.User && S.User.getMe) { const u = S.User.getMe(); if (u) me = u.id && (u.id.user || u.id._serialized || String(u.id)); }
      if (!me && S && S.StatusActions && S.StatusActions.getMyStatus) { me = "unknown"; }
    } catch (e) {}
    return { ok: true, store: !!S, connected: connected, me: me ? String(me) : null };
  } catch (e) {
    return { ok: false, reason: String(e) };
  }
}
"""

CHATS_JS = r"""
(cap) => {
  try {
    const S = window.__parleyResolve ? window.__parleyResolve(window.__parleyStore) : (window.Store || null);
    if (!S || !S.Chat || !S.Chat.getModelsArray) return [];
    return S.Chat.getModelsArray()
      .slice(0, cap)
      .map((c) => {
        try {
          const id = (c.id && (c.id._serialized || c.id.toString())) || "";
          const isGroup = id.indexOf("@g.us") > 0 || id.indexOf("@broadcast") > 0;
          let name = null;
          try { name = c.formattedTitle ? c.formattedTitle() : null; } catch (e) {}
          if (!name) name = c.name || id;
          let lastBody = "";
          try { if (c.lastMessage) lastBody = c.lastMessage.body || c.lastMessage.caption || ""; } catch (e) {}
          let ts = null;
          try { if (c.t) ts = typeof c.t === "number" ? c.t : (c.t.sec || c.t.low / 1000); } catch (e) {}
          return {
            id, name: String(name), is_group: isGroup,
            unread: c.unreadCount || 0, pinned: !!(c.pin || c.pinned),
            last_message: String(lastBody).slice(0, 200),
            last_timestamp: ts ? Number(ts) : null,
          };
        } catch (e) { return null; }
      })
      .filter((r) => r && r.id);
  } catch (e) { return []; }
}
"""

MESSAGES_JS = r"""
(args) => {
  const chatId = args.chatId, limit = args.limit;
  try {
    const S = window.__parleyResolve ? window.__parleyResolve(window.__parleyStore) : (window.Store || null);
    if (!S || !S.Msg || !S.Msg.getModelsArray) return { ok: false, reason: "no Msg store" };
    let chat = null;
    try { if (S.Chat && S.Chat.get) chat = S.Chat.get(chatId); } catch (e) {}
    let all = null;
    if (chat && chat.msgs && typeof chat.msgs.getModelsArray === "function") {
      all = chat.msgs.getModelsArray();
    } else if (S.Msg.getModelsArray) {
      all = S.Msg.getModelsArray().filter((m) => m.chat && m.chat.id && m.chat.id._serialized === chatId);
    }
    if (!all) return { ok: false, reason: "could not collect messages" };
    const out = all.slice(-limit).map((m) => {
      try {
        const mid = m.id && (m.id._serialized || m.id.toString());
        let who = "";
        try { if (m.author) who = m.author._serialized || m.author.user || String(m.author); } catch (e) {}
        const txt = m.body || m.caption || "";
        let ts = null;
        try { if (m.t) ts = typeof m.t === "number" ? m.t : m.t.sec; } catch (e) {}
        return {
          id: String(mid || ""), chat: chatId,
          author: who ? String(who) : (m.fromMe ? "me" : ""),
          text: String(txt).slice(0, 4000),
          timestamp: ts ? Number(ts) : null,
          from_me: !!m.fromMe,
          kind: m.type ? String(m.type) : "text",
        };
      } catch (e) { return null; }
    }).filter((r) => r && r.id);
    return { ok: true, messages: out };
  } catch (e) {
    return { ok: false, reason: String(e) };
  }
}
"""

SEND_JS = r"""
async (args) => {
  const chat = args.chat, text = args.text;
  const S = window.__parleyResolve ? window.__parleyResolve(window.__parleyStore) : (window.Store || null);
  const log = [];
  if (!S) return { ok: false, reason: "no store" };
  const trySend = async (fn) => { try { await fn(); return true; } catch (e) { log.push(String(e).slice(0, 140)); return false; } };
  if (S.Chat && typeof S.Chat.sendTextMsg === "function") {
    if (await trySend(() => S.Chat.sendTextMsg(chat, text))) return { ok: true, via: "Chat.sendTextMsg" };
  }
  if (S.Chat && typeof S.Chat.find === "function") {
    const c = await S.Chat.find(chat);
    if (c && typeof c.sendMessage === "function") {
      if (await trySend(() => c.sendMessage(text))) return { ok: true, via: "chat.sendMessage" };
    }
  }
  if (S.Msg && typeof S.Msg.sendTextMsg === "function") {
    if (await trySend(() => S.Msg.sendTextMsg(chat, text, {}))) return { ok: true, via: "Msg.sendTextMsg" };
  }
  return { ok: false, reason: log.slice(-3).join(" | ") || "no usable send api" };
}
"""

REACT_JS = r"""
async (args) => {
  const messageId = args.messageId, emoji = args.emoji;
  const S = window.__parleyResolve ? window.__parleyResolve(window.__parleyStore) : (window.Store || null);
  if (!S || !S.Msg || !S.Msg.get) return { ok: false, reason: "no Msg store" };
  let msg;
  try { msg = S.Msg.get(messageId); } catch (e) { return { ok: false, reason: "unknown message: " + messageId }; }
  if (!msg) return { ok: false, reason: "unknown message: " + messageId };
  const tries = [
    () => msg.react(emoji),
    () => S.Msg.sendReactToMessage(msg, null, emoji),
    () => S.Msg.addReactionToMessage(msg, emoji, { model: msg }),
  ];
  for (let i = 0; i < tries.length; i++) {
    try { await tries[i](); return { ok: true, via: i }; } catch (e) {}
  }
  return { ok: false, reason: "no usable react api" };
}
"""

REPLY_JS = r"""
async (args) => {
  const chat = args.chat, messageId = args.messageId, text = args.text;
  const S = window.__parleyResolve ? window.__parleyResolve(window.__parleyStore) : (window.Store || null);
  if (!S || !S.Msg || !S.Msg.get) return { ok: false, reason: "no Msg store" };
  let target;
  try { target = S.Msg.get(messageId); } catch (e) { return { ok: false, reason: "unknown message: " + messageId }; }
  if (!target) return { ok: false, reason: "unknown message: " + messageId };
  if (S.Chat && typeof S.Chat.sendTextMsg === "function") {
    try { await S.Chat.sendTextMsg(chat, text, { quotedMsg: target }); return { ok: true, via: "sendTextMsg quoted" }; } catch (e) {}
  }
  if (S.Chat && typeof S.Chat.find === "function") {
    try {
      const c = await S.Chat.find(chat);
      if (c && typeof c.sendMessage === "function") {
        await c.sendMessage(text, { quotedMsg: target });
        return { ok: true, via: "chat.sendMessage quoted" };
      }
    } catch (e) {}
  }
  return { ok: false, reason: "no quoted-send api" };
}
"""

DOM_CHATS_JS = r"""
(cap) => {
  try {
    const sel = '#pane-side [role="row"], [data-testid="chat-list"] [role="listitem"]';
    const nodes = document.querySelectorAll(sel);
    const out = [];
    for (const n of nodes) {
      if (out.length >= cap) break;
      const txt = (n.innerText || "").split("\n");
      out.push({ id: n.getAttribute("data-id") || String(out.length), name: txt[0] || "", last_message: txt.slice(1).join(" ") || "", dom: true });
    }
    return out;
  } catch (e) { return []; }
}
"""

CONTACTS_JS = r"""
() => {
  try {
    const S = window.__parleyResolve ? window.__parleyResolve(window.__parleyStore) : (window.Store || null);
    if (!S || !S.Contact || !S.Contact.getModelsArray) return [];
    return S.Contact.getModelsArray().slice(0, 500).map((c) => {
      try {
        const id = (c.id && (c.id._serialized || c.id.toString())) || "";
        const pn = (c.user && c.user.pushname) || c.pushname || null;
        let short = null;
        try { short = c.shortName || null; } catch (e) {}
        return { id, name: pn || c.name || id, is_group: id.indexOf("@g.us") > 0, pushname: pn, short };
      } catch (e) { return null; }
    }).filter((r) => r && r.id);
  } catch (e) { return []; }
}
"""

DOM_STATUS_JS = r"""
() => {
  try {
    const qr = document.querySelectorAll('canvas[aria-label*="QR"], [data-testid="qr-code"]').length;
    const pane = !!document.querySelector("#pane-side") || !!document.querySelector('[data-testid="chat-list"]');
    const loggedIn = qr === 0 && pane;
    return { dom: true, loggedIn, hasPane: pane };
  } catch (e) { return { dom: true, loggedIn: null, hasPane: false }; }
}
"""
