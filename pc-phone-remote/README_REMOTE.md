# Remote Access Without Same Wi-Fi

This version does not require Tailscale or router port forwarding.

Architecture:

```text
Phone app -> public relay server -> PC relay agent -> Windows command
```

The PC opens an outgoing connection to the relay, so the router does not need inbound ports.

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
