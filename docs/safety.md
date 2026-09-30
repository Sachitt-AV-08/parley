# Safety Notes

- parley **never** sees, stores or transmits your credentials, chats, contacts or session state. All traffic stays on `127.0.0.1`.
- Sends are paced and budgeted by design. Read operations never write.
- **Terms**: use your own account, your own device, your own automation — comply with local law and WhatsApp's ToS. The issues tracker is open for questions.
- If you expose the HTTP server beyond loopback, set `--token` and use TLS in front — and honestly, don't; keep it on `127.0.0.1`.