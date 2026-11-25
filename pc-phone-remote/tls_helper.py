"""Optional self-signed local HTTPS certificate generation & TLS wrapper for LAN PWA."""
from __future__ import annotations

import ipaddress
import os
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CERTS_DIR = APP_DIR / "certs"
CERT_FILE = CERTS_DIR / "server.crt"
KEY_FILE = CERTS_DIR / "server.key"


def _find_openssl() -> str | None:
    found = shutil.which("openssl")
    if found:
        return found
    if os.name == "nt":
        for cand in (
            Path(r"C:\Program Files\Git\usr\bin\openssl.exe"),
            Path(r"C:\Program Files\Git\mingw64\bin\openssl.exe"),
            Path(r"C:\Program Files (x86)\Git\usr\bin\openssl.exe"),
            Path(r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe"),
        ):
            if cand.exists():
                return str(cand)
    return None


def _build_san_entries(ips: list[str] | None = None) -> list[str]:
    entries = ["DNS:localhost", "IP:127.0.0.1"]
    seen = {"127.0.0.1"}
    for raw in ips or []:
        try:
            ip = str(ipaddress.ip_address(raw.strip()))
            if ip not in seen:
                seen.add(ip)
                entries.append(f"IP:{ip}")
        except ValueError:
            continue
    return entries


def ensure_local_tls_cert(ips: list[str] | None = None, force_regen: bool = False) -> tuple[Path, Path]:
    """Ensure a local self-signed RSA-2048 X.509 cert + private key exist with LAN SANs."""
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    if not force_regen and CERT_FILE.exists() and KEY_FILE.exists():
        return CERT_FILE, KEY_FILE

    san = ",".join(_build_san_entries(ips))
    openssl = _find_openssl()
    if openssl:
        cnf_text = (
            "[req]\n"
            "distinguished_name = dn\n"
            "x509_extensions = v3_ext\n"
            "prompt = no\n"
            "[dn]\n"
            "CN = PC Phone Remote Local\n"
            "[v3_ext]\n"
            "basicConstraints = CA:FALSE\n"
            "keyUsage = digitalSignature, keyEncipherment\n"
            "extendedKeyUsage = serverAuth\n"
            f"subjectAltName = {san}\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False, encoding="utf-8") as tf:
            tf.write(cnf_text)
            cnf_path = Path(tf.name)
        try:
            res = subprocess.run(
                [
                    openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-days", "825",
                    "-keyout", str(KEY_FILE),
                    "-out", str(CERT_FILE),
                    "-config", str(cnf_path),
                ],
                capture_output=True, text=True, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if res.returncode == 0 and CERT_FILE.exists() and KEY_FILE.exists():
                return CERT_FILE, KEY_FILE
            raise RuntimeError(res.stderr.strip() or "OpenSSL certificate generation failed")
        finally:
            try:
                cnf_path.unlink(missing_ok=True)
            except OSError:
                pass

    try:
        import datetime
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PC Phone Remote Local")])
        san_objs = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
        for raw in ips or []:
            try:
                san_objs.append(x509.IPAddress(ipaddress.ip_address(raw.strip())))
            except ValueError:
                pass
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(san_objs), critical=False)
            .sign(key, hashes.SHA256())
        )
        KEY_FILE.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        return CERT_FILE, KEY_FILE
    except ImportError:
        pass

    raise RuntimeError("Install OpenSSL (or Git for Windows / python cryptography) to generate a local HTTPS certificate")


def wrap_server_ssl(http_server, cert_path: Path = CERT_FILE, key_path: Path = KEY_FILE) -> None:
    """Wrap a ThreadingHTTPServer socket with TLS."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    http_server.socket = ctx.wrap_socket(http_server.socket, server_side=True)


def tls_status_snapshot() -> dict:
    return {
        "cert_exists": CERT_FILE.exists() and KEY_FILE.exists(),
        "cert_path": str(CERT_FILE),
        "openssl_available": _find_openssl() is not None,
    }
