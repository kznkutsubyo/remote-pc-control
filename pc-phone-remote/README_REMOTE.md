# Remote Access Without Same Wi-Fi

This version does not require Tailscale or router port forwarding.

Architecture:

```text
Phone app -> public relay server -> PC relay agent -> Windows command
```

The PC opens an outgoing connection to the relay, so the router does not need inbound ports for commands and file/text exchange. RDP sign-in is a separate connection and may need an RD Gateway.

Version 2 requires updating both `relay_server.py` and `relay_agent.py`. Deploy their companion modules (`app.py`, `companion.py`) alongside them. One relay instance serves one PC. Use a separate URL/instance for each remote PC.

## 1. Run the relay on a public server

On a VPS or hosting platform with HTTPS:

```powershell
$env:RELAY_PIN = "<your-pin>"
$env:RELAY_AGENT_TOKEN = "replace-with-a-long-random-token"
python relay_server.py --host 0.0.0.0 --port 8080
```

Put HTTPS in front of it with your hosting provider, reverse proxy, or load balancer.

## 2. Run the PC agent

On this Windows PC:

```powershell
cd "pc-phone-remote"
setx RELAY_URL "https://your-relay.example.com"
setx RELAY_AGENT_TOKEN "replace-with-the-same-long-random-token"
python relay_agent.py
```

## 3. Configure the Android app

In the app, put the full relay URL into the IP field:

```text
https://your-relay.example.com
```

The port field is ignored when the IP field starts with `http://` or `https://`.

PIN remains:

```text
use the same PIN you set in RELAY_PIN
```

## Notes

- Do not expose `app.py` directly to the internet.
- Use HTTPS for the relay URL.
- Use a long random `RELAY_AGENT_TOKEN`; it is the secret that lets only your PC fetch commands.
- The token must be at least 24 characters and is sent in a header, not a URL.
- Files are limited to 8 MiB, text to 64 KiB. Requests are temporarily buffered in memory; run your own trusted relay. HTTPS is transport encryption, not end-to-end encryption through the relay.
- Requests wait up to 22 seconds for the agent; unclaimed expired jobs are dropped. A lost response after execution can leave the outcome uncertain, so clients do not automatically retry commands.
- Configure the reverse proxy for request bodies of at least 12 MiB and a response timeout greater than 30 seconds. PC and relay clocks must be synchronized for job expiry.
